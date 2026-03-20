import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    pass


class LLMConfigurationError(LLMServiceError):
    pass


class LLMUpstreamError(LLMServiceError):
    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model_name: str | None = None,
        endpoint: str | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
        body_preview: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model_name = model_name
        self.endpoint = endpoint
        self.status_code = status_code
        self.request_id = request_id
        self.error_code = error_code
        self.error_type = error_type
        self.body_preview = body_preview

    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f'provider={self.provider}')
        if self.model_name:
            parts.append(f'model={self.model_name}')
        if self.status_code is not None:
            parts.append(f'status={self.status_code}')
        if self.error_code:
            parts.append(f'error_code={self.error_code}')
        if self.error_type:
            parts.append(f'error_type={self.error_type}')
        if self.request_id:
            parts.append(f'request_id={self.request_id}')
        if self.endpoint:
            parts.append(f'endpoint={self.endpoint}')
        if self.body_preview:
            parts.append(f'body={self.body_preview}')
        return ' | '.join(parts)


@dataclass(frozen=True)
class ModelDescriptor:
    key: str
    provider: str
    model_name: str


def list_supported_models() -> list[ModelDescriptor]:
    return [
        ModelDescriptor(key='qwen', provider='qwen', model_name=settings.qwen_model),
        ModelDescriptor(key='deepseek', provider='deepseek', model_name=settings.deepseek_model),
    ]


def generate_completion(
    *,
    model_key: str,
    prompt: str,
    history_messages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    descriptor = _get_model_descriptor(model_key)
    endpoint, api_key = _resolve_endpoint_and_key(descriptor.key)

    if not api_key:
        raise LLMConfigurationError(f'{descriptor.provider} API key is not configured')

    payload = {
        'model': descriptor.model_name,
        'messages': [
            *_normalize_history_messages(history_messages or []),
            {'role': 'user', 'content': prompt},
        ],
    }

    data = _request_completion(
        provider=descriptor.provider,
        model_name=descriptor.model_name,
        endpoint=endpoint,
        api_key=api_key,
        payload=payload,
    )
    content = _extract_content(data)
    citations = _extract_citations(data, content)
    generated_at = _extract_generated_at(data)

    return {
        'model_name': descriptor.model_name,
        'generated_at': generated_at,
        'content': content,
        'citations': citations,
    }


def _normalize_history_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get('role') or '').strip()
        content = str(item.get('content') or '').strip()
        if role not in {'system', 'user', 'assistant'} or not content:
            continue
        normalized.append({'role': role, 'content': content})
    return normalized


def _get_model_descriptor(model_key: str) -> ModelDescriptor:
    for descriptor in list_supported_models():
        if descriptor.key == model_key:
            return descriptor
    raise LLMConfigurationError(f'Unsupported model: {model_key}')


def _resolve_endpoint_and_key(model_key: str) -> tuple[str, str]:
    if model_key == 'qwen':
        return (_resolve_qwen_endpoint(settings.qwen_base_url), settings.qwen_api_key)
    if model_key == 'deepseek':
        return (_join_url(settings.deepseek_base_url, '/chat/completions'), settings.deepseek_api_key)
    raise LLMConfigurationError(f'Unsupported model: {model_key}')


def _resolve_qwen_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip('/')
    if normalized.endswith('/compatible-mode/v1'):
        return f'{normalized}/chat/completions'
    return _join_url(normalized, '/compatible-mode/v1/chat/completions')


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _request_completion(
    *,
    provider: str,
    model_name: str,
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    try:
        with httpx.Client(timeout=settings.chat_timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        error = LLMUpstreamError(
            f'Failed to reach model provider: {exc}',
            provider=provider,
            model_name=model_name,
            endpoint=endpoint,
        )
        logger.exception('LLM provider request failed: %s', error)
        raise error from exc

    if response.status_code >= 400:
        error = _build_upstream_http_error(
            provider=provider,
            model_name=model_name,
            endpoint=endpoint,
            response=response,
        )
        logger.error('LLM provider returned error response: %s', error)
        raise error

    try:
        return response.json()
    except ValueError as exc:
        error = LLMUpstreamError(
            'Model provider returned invalid JSON',
            provider=provider,
            model_name=model_name,
            endpoint=endpoint,
            status_code=response.status_code,
            request_id=_extract_request_id(response),
            body_preview=_compact_text(response.text, limit=500),
        )
        logger.error('LLM provider returned invalid JSON: %s', error)
        raise error from exc


def _build_upstream_http_error(
    *,
    provider: str,
    model_name: str,
    endpoint: str,
    response: httpx.Response,
) -> LLMUpstreamError:
    detail = _extract_error_detail(response)
    request_id = _extract_request_id(response)
    error_code = _extract_error_code(response)
    error_type = _extract_error_type(response)
    body_preview = _extract_body_preview(response)
    message = f'Model provider returned HTTP {response.status_code}: {detail}'
    return LLMUpstreamError(
        message,
        provider=provider,
        model_name=model_name,
        endpoint=endpoint,
        status_code=response.status_code,
        request_id=request_id,
        error_code=error_code,
        error_type=error_type,
        body_preview=body_preview,
    )


def _extract_error_detail(response: httpx.Response) -> str:
    body = _safe_json(response)
    if isinstance(body, dict):
        error = body.get('error')
        if isinstance(error, dict):
            for key in ('message', 'msg', 'detail', 'code'):
                value = error.get(key)
                if value:
                    return str(value)
            return _compact_text(json.dumps(error, ensure_ascii=False), limit=300)
        if error:
            return _compact_text(str(error), limit=300)

        for key in ('message', 'msg', 'detail'):
            value = body.get(key)
            if value:
                return _compact_text(str(value), limit=300)

        return _compact_text(json.dumps(body, ensure_ascii=False), limit=300)

    if body is not None:
        return _compact_text(str(body), limit=300)

    return _compact_text(response.text or 'unknown error', limit=300) or 'unknown error'


def _extract_error_code(response: httpx.Response) -> str | None:
    body = _safe_json(response)
    if isinstance(body, dict):
        error = body.get('error')
        if isinstance(error, dict):
            for key in ('code', 'error_code'):
                value = error.get(key)
                if value is not None:
                    return str(value)
        for key in ('code', 'error_code'):
            value = body.get(key)
            if value is not None:
                return str(value)
    return None


def _extract_error_type(response: httpx.Response) -> str | None:
    body = _safe_json(response)
    if isinstance(body, dict):
        error = body.get('error')
        if isinstance(error, dict):
            for key in ('type', 'error_type'):
                value = error.get(key)
                if value:
                    return str(value)
        for key in ('type', 'error_type'):
            value = body.get(key)
            if value:
                return str(value)
    return None


def _extract_body_preview(response: httpx.Response) -> str | None:
    body = _safe_json(response)
    if body is not None:
        return _compact_text(json.dumps(body, ensure_ascii=False), limit=500)
    return _compact_text(response.text, limit=500)


def _extract_request_id(response: httpx.Response) -> str | None:
    for key in ('x-request-id', 'request-id', 'x-dashscope-request-id', 'trace-id'):
        value = response.headers.get(key)
        if value:
            return value.strip()
    return None


def _safe_json(response: httpx.Response) -> Any | None:
    try:
        return response.json()
    except ValueError:
        return None


def _compact_text(value: str | None, *, limit: int) -> str | None:
    if not value:
        return None
    compact = re.sub(r'\s+', ' ', value).strip()
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return f'{compact[: limit - 3]}...'


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get('choices')
    if not isinstance(choices, list) or not choices:
        raise LLMUpstreamError('No choices returned from model provider')

    message = choices[0].get('message')
    if not isinstance(message, dict):
        raise LLMUpstreamError('Invalid message format from model provider')

    content = message.get('content', '')
    text = _normalize_content(content)
    if not text:
        raise LLMUpstreamError('Model returned empty content')
    return text


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if not isinstance(item, dict):
                continue
            for key in ('text', 'content', 'value'):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    chunks.append(value)
                    break
        return '\n'.join(chunks).strip()

    return str(content).strip()


def _extract_generated_at(payload: dict[str, Any]) -> datetime:
    created = payload.get('created')
    if isinstance(created, (int, float)):
        return datetime.utcfromtimestamp(created)
    return datetime.utcnow()


def _extract_citations(payload: dict[str, Any], content: str) -> list[str]:
    citations: list[str] = []

    for key in ('citations', 'references', 'sources'):
        citations.extend(_normalize_citation_items(payload.get(key)))

    choices = payload.get('choices')
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get('message')
        if isinstance(message, dict):
            for key in ('citations', 'references', 'sources'):
                citations.extend(_normalize_citation_items(message.get(key)))

    if not citations:
        citations.extend(_extract_links_from_text(content))

    return _dedupe_preserve_order(citations)[:30]


def _normalize_citation_items(raw: Any) -> list[str]:
    if not raw:
        return []

    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []

    if not isinstance(raw, list):
        return []

    normalized: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append(text)
            continue

        if not isinstance(item, dict):
            continue

        title = item.get('title') or item.get('name') or item.get('source')
        url = item.get('url') or item.get('link')
        if title and url:
            normalized.append(f'{title} - {url}')
            continue
        if url:
            normalized.append(str(url))
            continue
        if title:
            normalized.append(str(title))

    return normalized


def _extract_links_from_text(text: str) -> list[str]:
    if not text:
        return []

    markdown_links = re.findall(r'\[[^\]]+\]\((https?://[^\s)]+)\)', text)
    plain_links = re.findall(r'https?://[^\s)]+', text)
    return [link.strip() for link in markdown_links + plain_links if link.strip()]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
