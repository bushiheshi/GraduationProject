from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings


class CodeDetectionConfigurationError(RuntimeError):
    """配置或运行环境不满足要求时抛出。"""


class CodeDetectionUnavailableError(RuntimeError):
    """模型加载或推理失败时抛出。"""


class DroidDetectBinaryModel:
    """按照模型卡描述手工还原二分类结构。

    论文模型不是标准的 AutoModelForSequenceClassification，而是：
    1. ModernBERT 作为文本编码器
    2. 对最后一层隐藏状态做 mean pooling
    3. 再经过 Linear -> ReLU -> Linear 输出二分类 logits
    """

    def __init__(self, *, torch_module, transformer_model, hidden_size: int, projection_dim: int, num_classes: int):
        torch = torch_module
        encoder = transformer_model
        text_projection = torch.nn.Linear(hidden_size, projection_dim)
        classifier = torch.nn.Linear(projection_dim, num_classes)

        class _Wrapper(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.text_encoder = encoder
                self.text_projection = text_projection
                self.activation = torch.nn.ReLU()
                self.classifier = classifier

            def forward(self, **kwargs):
                outputs = self.text_encoder(**kwargs)
                last_hidden_state = outputs.last_hidden_state
                pooled = last_hidden_state.mean(dim=1)
                projected = self.text_projection(pooled)
                activated = self.activation(projected)
                logits = self.classifier(activated)
                return {'logits': logits}

        self.module = _Wrapper()

    def eval(self) -> None:
        self.module.eval()

    def load_state_dict(self, state_dict: dict[str, Any], *, strict: bool = False):
        return self.module.load_state_dict(state_dict, strict=strict)

    def __call__(self, **kwargs):
        return self.module(**kwargs)


def _extract_state_dict(raw_state: Any) -> dict[str, Any]:
    if isinstance(raw_state, dict):
        nested_state = raw_state.get('state_dict')
        if isinstance(nested_state, dict):
            return nested_state
        return raw_state
    raise CodeDetectionUnavailableError('代码检测模型权重格式不受支持。')


def _filter_unused_training_state(state_dict: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    ignored_prefix = 'additional_loss.'
    filtered_state = {
        key: value
        for key, value in state_dict.items()
        if not key.startswith(ignored_prefix)
    }
    ignored_keys = [key for key in state_dict if key.startswith(ignored_prefix)]
    return filtered_state, ignored_keys


def _infer_classifier_shape(state_dict: dict[str, Any], config_data: dict[str, Any]) -> tuple[int, int]:
    projection_weight = state_dict.get('text_projection.weight')
    projection_bias = state_dict.get('text_projection.bias')
    classifier_weight = state_dict.get('classifier.weight')

    if projection_weight is not None:
        projection_dim = int(projection_weight.shape[0])
    elif projection_bias is not None:
        projection_dim = int(projection_bias.shape[0])
    elif classifier_weight is not None:
        projection_dim = int(classifier_weight.shape[1])
    else:
        projection_dim = int(config_data.get('projection_dim') or 256)

    if classifier_weight is not None:
        num_classes = int(classifier_weight.shape[0])
    else:
        num_classes = int(config_data.get('num_classes') or 2)

    return projection_dim, num_classes


@lru_cache
def _load_detection_bundle() -> dict[str, Any]:
    """懒加载检测模型，避免机器没装推理依赖时导致整个 FastAPI 启动失败。"""
    settings = get_settings()

    try:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - 依赖缺失时走接口错误分支
        raise CodeDetectionConfigurationError(
            '代码检测依赖未安装，请先安装 transformers、torch 和 huggingface_hub。'
        ) from exc

    try:
        tokenizer = AutoTokenizer.from_pretrained(settings.code_detect_model_id)
        base_model = AutoModel.from_pretrained(settings.code_detect_base_model_id)
        config_path = Path(hf_hub_download(settings.code_detect_model_id, 'config.json'))
        weights_path = Path(hf_hub_download(settings.code_detect_model_id, 'pytorch_model.bin'))
    except Exception as exc:  # noqa: BLE001
        raise CodeDetectionUnavailableError(
            f'代码检测模型下载或基础模型加载失败：{settings.code_detect_model_id}'
        ) from exc

    try:
        config_data = json.loads(config_path.read_text(encoding='utf-8'))
        raw_state = torch.load(weights_path, map_location='cpu')
        checkpoint_state = _extract_state_dict(raw_state)
        state_dict, ignored_training_keys = _filter_unused_training_state(checkpoint_state)
        projection_dim, num_classes = _infer_classifier_shape(state_dict, config_data)
        hidden_size = int(getattr(base_model.config, 'hidden_size'))

        model = DroidDetectBinaryModel(
            torch_module=torch,
            transformer_model=base_model,
            hidden_size=hidden_size,
            projection_dim=projection_dim,
            num_classes=num_classes,
        )

        load_result = model.load_state_dict(state_dict, strict=False)
        model.eval()
    except Exception as exc:  # noqa: BLE001
        raise CodeDetectionUnavailableError(
            f'代码检测模型权重装载失败：{settings.code_detect_model_id}'
        ) from exc

    return {
        'torch': torch,
        'tokenizer': tokenizer,
        'model': model,
        'label_map': config_data.get('id2label') or {0: 'HUMAN_GENERATED', 1: 'MACHINE_GENERATED'},
        'load_result': {
            'missing_keys': list(getattr(load_result, 'missing_keys', [])),
            'unexpected_keys': list(getattr(load_result, 'unexpected_keys', [])),
            'ignored_training_keys': ignored_training_keys,
            'projection_dim': projection_dim,
            'num_classes': num_classes,
        },
    }


def detect_code_authorship(*, code: str, filename: str | None = None, language: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    normalized_code = _normalize_code(code)
    if not normalized_code:
        raise CodeDetectionConfigurationError('待检测代码不能为空。')

    bundle = _load_detection_bundle()
    torch = bundle['torch']
    tokenizer = bundle['tokenizer']
    model = bundle['model']

    machine_label_index, human_label_index = _resolve_label_indices(bundle['label_map'])
    chunks = _split_code_into_chunks(
        normalized_code,
        chunk_chars=settings.code_detect_chunk_chars,
        overlap_chars=settings.code_detect_chunk_overlap_chars,
    )

    weighted_machine_probability = 0.0
    weighted_human_probability = 0.0
    weighted_total = 0
    chunk_scores: list[dict[str, Any]] = []

    # 长代码通常会超过模型最大输入长度，这里先按字符切块，再交给 tokenizer 截断到安全长度。
    for index, chunk in enumerate(chunks, start=1):
        encoded = tokenizer(
            chunk['text'],
            return_tensors='pt',
            truncation=True,
            max_length=settings.code_detect_max_length,
        )

        try:
            with torch.no_grad():
                outputs = model(**encoded)
                logits = outputs['logits']
                probabilities = torch.softmax(logits, dim=-1)[0].tolist()
        except Exception as exc:  # noqa: BLE001
            raise CodeDetectionUnavailableError('代码检测模型推理失败。') from exc

        machine_probability = float(probabilities[machine_label_index])
        human_probability = float(probabilities[human_label_index])
        chunk_length = chunk['end_offset'] - chunk['start_offset']

        weighted_machine_probability += machine_probability * chunk_length
        weighted_human_probability += human_probability * chunk_length
        weighted_total += chunk_length
        chunk_scores.append(
            {
                'chunk_index': index,
                'start_offset': chunk['start_offset'],
                'end_offset': chunk['end_offset'],
                'machine_generated_probability': round(machine_probability, 6),
                'human_generated_probability': round(human_probability, 6),
            }
        )

    if weighted_total <= 0:
        raise CodeDetectionUnavailableError('代码检测未能生成有效分片结果。')

    machine_probability = weighted_machine_probability / weighted_total
    human_probability = weighted_human_probability / weighted_total
    label = 'machine_generated' if machine_probability >= settings.code_detect_threshold else 'human_generated'
    confidence = machine_probability if label == 'machine_generated' else human_probability

    missing_keys = bundle['load_result']['missing_keys']
    unexpected_keys = bundle['load_result']['unexpected_keys']

    # 这里返回“风险判断 + 可解释分片分数”，方便后续在教师端展示证据，而不是只给一个黑盒结论。
    return {
        'model_id': settings.code_detect_model_id,
        'filename': filename,
        'language': language,
        'label': label,
        'confidence': round(confidence, 6),
        'threshold': round(settings.code_detect_threshold, 6),
        'machine_generated_probability': round(machine_probability, 6),
        'human_generated_probability': round(human_probability, 6),
        'code_length': len(normalized_code),
        'chunk_count': len(chunk_scores),
        'explanation': _build_explanation(
            label=label,
            machine_probability=machine_probability,
            human_probability=human_probability,
            threshold=settings.code_detect_threshold,
            missing_keys=missing_keys,
            unexpected_keys=unexpected_keys,
        ),
        'chunk_scores': chunk_scores,
    }


def _normalize_code(code: str) -> str:
    return code.replace('\r\n', '\n').strip()


def _split_code_into_chunks(code: str, *, chunk_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    if chunk_chars <= 0:
        raise CodeDetectionConfigurationError('code_detect_chunk_chars 必须大于 0。')
    if overlap_chars < 0:
        raise CodeDetectionConfigurationError('code_detect_chunk_overlap_chars 不能小于 0。')
    if overlap_chars >= chunk_chars:
        raise CodeDetectionConfigurationError('code_detect_chunk_overlap_chars 必须小于 code_detect_chunk_chars。')

    if len(code) <= chunk_chars:
        return [{'text': code, 'start_offset': 0, 'end_offset': len(code)}]

    chunks: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(code):
        end = min(cursor + chunk_chars, len(code))
        chunks.append(
            {
                'text': code[cursor:end],
                'start_offset': cursor,
                'end_offset': end,
            }
        )
        if end >= len(code):
            break
        cursor = end - overlap_chars

    return chunks


def _resolve_label_indices(id2label: dict[int, str] | dict[str, str]) -> tuple[int, int]:
    """兼容不同模型卡的 id2label 形式，尽量自动找到机器生成和人工编写的标签索引。"""
    normalized_map: dict[int, str] = {}
    for key, value in id2label.items():
        normalized_map[int(key)] = str(value).upper()

    machine_index = next(
        (
            index
            for index, label in normalized_map.items()
            if 'MACHINE' in label or 'AI' in label
        ),
        1,
    )
    human_index = next(
        (
            index
            for index, label in normalized_map.items()
            if 'HUMAN' in label
        ),
        0,
    )
    return machine_index, human_index


def _build_explanation(
    *,
    label: str,
    machine_probability: float,
    human_probability: float,
    threshold: float,
    missing_keys: list[str],
    unexpected_keys: list[str],
) -> str:
    explanation = (
        f'模型判定更偏向 AI 生成代码；机器生成概率为 {machine_probability:.2%}，超过阈值 {threshold:.2%}。'
        if label == 'machine_generated'
        else f'模型判定更偏向人工编写代码；人工编写概率为 {human_probability:.2%}，机器生成概率为 {machine_probability:.2%}。'
    )

    # 加一点装载状态说明，便于后续排查自定义模型权重是否完整对齐。
    if missing_keys or unexpected_keys:
        explanation += (
            f' 权重装载信息：missing_keys={len(missing_keys)}，unexpected_keys={len(unexpected_keys)}。'
        )
    return explanation
