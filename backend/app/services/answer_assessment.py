import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings


DEFAULT_EMBEDDING_MODEL = 'BAAI/bge-small-zh-v1.5'
DEFAULT_INDEX_DIRNAME = 'vector_index'
QUERY_INSTRUCTION = '为这个句子生成表示以用于检索相关教材内容：'

ENGLISH_TOKEN_RE = re.compile(r'[a-zA-Z][a-zA-Z0-9_+#.-]{1,}')
CHINESE_SEGMENT_RE = re.compile(r'[\u4e00-\u9fff]{2,}')
SENTENCE_SPLIT_RE = re.compile(r'[。！？；;!?\n]+')
CHINESE_STOPWORDS = {
    '我们',
    '你们',
    '他们',
    '这个',
    '那个',
    '因为',
    '所以',
    '如果',
    '然后',
    '就是',
    '可以',
    '需要',
    '通过',
    '进行',
    '其中',
    '一个',
    '一种',
    '一些',
    '以及',
    '或者',
    '但是',
    '并且',
    '首先',
    '其次',
    '最后',
    '学生',
    '老师',
    '答案',
    '问题',
    '内容',
    '相关',
}


class AssessmentResourceError(RuntimeError):
    """Raised when assessment resources or model dependencies are unavailable."""


def assess_answer_credibility(
    *,
    answer_text: str,
    question_text: str | None = None,
    chapter: str | None = None,
    section: str | None = None,
    max_order: int | None = None,
    semantic_top_k: int | None = None,
    report_top_k: int | None = None,
    ai_rate: float | None = None,
    ai_source: str | None = None,
) -> dict[str, Any]:
    answer_text = (answer_text or '').strip()
    if not answer_text:
        raise ValueError('Answer text is empty.')

    settings = get_settings()
    kb_dir = resolve_kb_dir(settings.assessment_kb_dir)
    chunks = load_jsonl(kb_dir / 'kb_chunks.jsonl')
    outline = json.loads((kb_dir / 'outline.json').read_text(encoding='utf-8'))

    progress_max_order = resolve_max_order(
        chunks=chunks,
        outline=outline,
        max_order=max_order,
        chapter=chapter,
        section=section,
    )
    in_scope_chunks = [chunk for chunk in chunks if chunk['order'] <= progress_max_order]
    future_chunks = [chunk for chunk in chunks if chunk['order'] > progress_max_order]

    semantic_index = get_semantic_index(
        str(kb_dir),
        settings.assessment_embedding_model or DEFAULT_EMBEDDING_MODEL,
    )

    normalized_ai_rate = clamp(ai_rate, 0.0, 1.0) if ai_rate is not None else None
    return compute_credibility(
        answer_text=answer_text,
        question_text=question_text,
        in_scope_chunks=in_scope_chunks,
        future_chunks=future_chunks,
        semantic_index=semantic_index,
        ai_rate=normalized_ai_rate,
        ai_source=ai_source,
        top_k=semantic_top_k or settings.assessment_semantic_top_k,
        report_top_k=report_top_k or settings.assessment_report_top_k,
        max_order=progress_max_order,
    )


def build_teacher_report(*, result: dict[str, Any], answer_text: str, question_text: str | None = None) -> str:
    metric_labels = {
        'support_coverage': '教材支撑覆盖度',
        'support_density': '教材支撑密度',
        'scope_alignment': '范围对齐度',
        'answer_specificity': '答案具体度',
        'evidence_consistency': '证据一致性',
        'ai_rate': 'AI 率',
        'ai_penalty': 'AI 惩罚',
    }
    lines = [
        '# 答案可信度评估报告',
        '',
        '## 一、结论摘要',
        '',
        f"- 综合得分：**{result['score']}**",
        f"- 可信度等级：**{result['label']}**",
        f"- 风险标签：{', '.join(result['risk_flags'])}",
        f"- 评估方法：`{result['method']['retrieval']}`",
        f"- 向量模型：`{result['method']['embedding_model']}`",
        f"- AI率来源：`{result['method']['ai_source'] or '未提供'}`",
        '',
        '## 二、问题与答案',
        '',
    ]
    if question_text:
        lines.extend(['### 题目', '', question_text.strip(), ''])
    lines.extend(['### 学生答案', '', answer_text.strip(), ''])

    lines.extend(['## 三、量化指标', ''])
    for key, value in result['metrics'].items():
        lines.append(f'- {metric_labels.get(key, key)}: `{value}`')

    lines.extend(['', '## 四、教材支撑证据', ''])
    support_chunks = result.get('supporting_chunks') or []
    if support_chunks:
        for item in support_chunks:
            title = ' / '.join(
                part for part in [item.get('chapter'), item.get('section'), item.get('topic')] if part
            ) or '未识别标题'
            lines.extend(
                [
                    f"### {item['chunk_id']} | {title}",
                    '',
                    f"- pages: `{item['page_start']}-{item['page_end']}`",
                    f"- semantic_score: `{item['semantic_score']}`",
                    f"- lexical_score: `{item['lexical_score']}`",
                    f"- combined_score: `{item['combined_score']}`",
                    f"- overlap: {', '.join(item.get('overlap') or [])}",
                    '',
                    item['snippet'],
                    '',
                ]
            )
    else:
        lines.extend(['未找到明显教材支撑片段。', ''])

    future_chunks = result.get('future_reference_chunks') or []
    lines.extend(['## 五、超纲风险检查', ''])
    if future_chunks:
        lines.append('以下片段位于当前学习进度之后，但与答案仍然有一定相关性：')
        lines.append('')
        for item in future_chunks:
            title = ' / '.join(
                part for part in [item.get('chapter'), item.get('section'), item.get('topic')] if part
            ) or '未识别标题'
            lines.extend(
                [
                    f"### {item['chunk_id']} | {title}",
                    '',
                    f"- pages: `{item['page_start']}-{item['page_end']}`",
                    f"- combined_score: `{item['combined_score']}`",
                    '',
                    item['snippet'],
                    '',
                ]
            )
    else:
        lines.extend(['未发现明显超出当前进度的高相关教材片段。', ''])

    lines.extend(['## 六、教师建议', '', build_teacher_recommendation(result), ''])
    return '\n'.join(lines)


def build_student_assessment_summary(result: dict[str, Any]) -> dict[str, Any]:
    shortcomings = build_student_shortcomings(result)
    if not shortcomings:
        shortcomings = ['暂未发现明显不足，建议继续核对题目要求和关键概念是否完整。']

    return {
        'score': result['score'],
        'label': result['label'],
        'risk_flags': result.get('risk_flags') or [],
        'main_shortcomings': shortcomings,
        'advice': build_student_advice(result, shortcomings),
    }


def build_student_shortcomings(result: dict[str, Any]) -> list[str]:
    metrics = result.get('metrics') or {}
    flags = set(result.get('risk_flags') or [])
    shortcomings: list[str] = []

    support_coverage = float(metrics.get('support_coverage') or 0.0)
    support_density = float(metrics.get('support_density') or 0.0)
    scope_alignment = float(metrics.get('scope_alignment') or 0.0)
    answer_specificity = float(metrics.get('answer_specificity') or 0.0)
    evidence_consistency = float(metrics.get('evidence_consistency') or 0.0)
    ai_rate = metrics.get('ai_rate')

    if support_coverage < 0.2 or '教材支撑较弱' in flags:
        shortcomings.append('答案中的关键词和教材知识点对应较少，建议补充题目涉及的核心概念或依据。')
    elif support_coverage < 0.4 or '教材支撑一般' in flags:
        shortcomings.append('答案与教材知识点有一定关联，但支撑还不够充分。')

    if support_density < 0.55:
        shortcomings.append('可参考的教材片段相关度偏低，建议让答案更贴近当前章节内容。')

    if scope_alignment < 0.6:
        shortcomings.append('答案可能引用了当前学习进度之外的内容，建议优先使用课堂已学方法表述。')

    if answer_specificity < 0.45:
        shortcomings.append('答案内容偏短或信息密度不足，建议补充关键步骤、变量含义或判断依据。')

    if evidence_consistency < 0.55:
        shortcomings.append('答案内部表述与教材证据的一致性不足，建议检查概念使用是否准确。')

    if isinstance(ai_rate, (int, float)) and ai_rate >= 0.8:
        shortcomings.append('答案存在较高 AI 生成风险，建议加入自己的推导过程和修改痕迹。')
    elif isinstance(ai_rate, (int, float)) and ai_rate >= 0.5:
        shortcomings.append('答案可能有 AI 辅助痕迹，建议确认每一步自己都能解释清楚。')

    return shortcomings[:4]


def build_student_advice(result: dict[str, Any], shortcomings: list[str]) -> str:
    label = result.get('label')
    if label in {'高可信', '中等可信'} and len(shortcomings) <= 1:
        return '整体情况尚可，提交前可以再检查题目要求是否全部覆盖，并补充必要的关键步骤。'
    if label == '存疑':
        return '建议先根据上面的不足逐条修改，重点补充与教材知识点对应的说明和关键逻辑。'
    return '建议重新对照题目和课堂内容整理答案，先写清楚核心思路，再补充关键语句或步骤。'


def resolve_kb_dir(configured_kb_dir: str | None) -> Path:
    if configured_kb_dir:
        kb_dir = Path(configured_kb_dir)
        if not kb_dir.is_absolute():
            kb_dir = Path(__file__).resolve().parents[2] / kb_dir
    else:
        kb_dir = Path(__file__).resolve().parents[1] / 'resources' / 'textbook_kb'

    kb_dir = kb_dir.resolve()
    required_files = [
        kb_dir / 'kb_chunks.jsonl',
        kb_dir / 'outline.json',
        kb_dir / DEFAULT_INDEX_DIRNAME / 'index_meta.json',
        kb_dir / DEFAULT_INDEX_DIRNAME / 'chunk_embeddings.npy',
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise AssessmentResourceError(f'Assessment KB resources are missing: {", ".join(missing)}')
    return kb_dir


def resolve_max_order(
    *,
    chunks: list[dict],
    outline: list[dict],
    max_order: int | None,
    chapter: str | None,
    section: str | None,
) -> int:
    if max_order is not None:
        if max_order < 0:
            raise ValueError('max_order must be greater than or equal to 0.')
        return max_order

    if not chapter:
        return max(chunk['order'] for chunk in chunks)

    target_first_page = None
    for item in outline:
        if item['chapter'] != chapter:
            continue
        if section and item.get('section') != section:
            continue
        target_first_page = item['last_page']

    if target_first_page is None:
        raise ValueError('Could not find the requested chapter/section in assessment outline.')

    eligible = [chunk['order'] for chunk in chunks if chunk['page_end'] <= target_first_page]
    if not eligible:
        raise ValueError('No KB chunks matched the requested progress bound.')
    return max(eligible)


@lru_cache(maxsize=4)
def get_semantic_index(kb_dir_value: str, model_name: str) -> dict[str, Any]:
    kb_dir = Path(kb_dir_value)
    index_dir = kb_dir / DEFAULT_INDEX_DIRNAME
    meta_path = index_dir / 'index_meta.json'
    embedding_path = index_dir / 'chunk_embeddings.npy'

    try:
        import numpy as np
    except ImportError as exc:
        raise AssessmentResourceError('numpy is required for assessment vector index loading.') from exc

    metadata = json.loads(meta_path.read_text(encoding='utf-8'))
    embeddings = np.load(embedding_path)
    chunks = load_jsonl(kb_dir / 'kb_chunks.jsonl')
    indexed_model_name = metadata.get('model_name') or DEFAULT_EMBEDDING_MODEL
    effective_model_name = model_name or indexed_model_name
    if effective_model_name != indexed_model_name:
        raise AssessmentResourceError(
            f'Assessment vector index was built with {indexed_model_name}, '
            f'but {effective_model_name} was requested. Rebuild the index before switching models.'
        )
    return {
        'model_name': effective_model_name,
        'embeddings': embeddings,
        'chunks': chunks,
        'index_dir': index_dir,
    }


def compute_credibility(
    *,
    answer_text: str,
    question_text: str | None,
    in_scope_chunks: list[dict],
    future_chunks: list[dict],
    semantic_index: dict[str, Any],
    ai_rate: float | None,
    ai_source: str | None,
    top_k: int,
    report_top_k: int,
    max_order: int,
) -> dict[str, Any]:
    query_text = '\n'.join(part for part in [question_text, answer_text] if part)
    answer_tokens = tokenize_text(answer_text)
    query_tokens = tokenize_text(query_text)

    in_scope_ranked = score_chunks(
        query_text=query_text,
        query_tokens=query_tokens,
        chunks=in_scope_chunks,
        semantic_index=semantic_index,
        top_k=top_k,
    )
    future_ranked = score_chunks(
        query_text=query_text,
        query_tokens=query_tokens,
        chunks=future_chunks,
        semantic_index=semantic_index,
        top_k=top_k,
    )

    top_support = in_scope_ranked[:report_top_k]
    top_future = [item for item in future_ranked if item['combined_score'] > 0][:report_top_k]

    support_coverage = compute_support_coverage(answer_tokens, top_support)
    support_density = compute_support_density(top_support)
    scope_alignment = compute_scope_alignment(top_support, top_future)
    answer_specificity = compute_answer_specificity(answer_text, answer_tokens)
    evidence_consistency = compute_evidence_consistency(top_support)

    base_score = (
        0.38 * support_coverage
        + 0.20 * support_density
        + 0.18 * scope_alignment
        + 0.12 * answer_specificity
        + 0.12 * evidence_consistency
    )
    ai_penalty = 0.18 * ai_rate if ai_rate is not None else 0.0
    final_score = clamp(base_score - ai_penalty, 0.0, 1.0)

    return {
        'score': round(final_score * 100, 2),
        'label': classify_score(final_score),
        'metrics': {
            'support_coverage': round(support_coverage, 4),
            'support_density': round(support_density, 4),
            'scope_alignment': round(scope_alignment, 4),
            'answer_specificity': round(answer_specificity, 4),
            'evidence_consistency': round(evidence_consistency, 4),
            'ai_rate': None if ai_rate is None else round(ai_rate, 4),
            'ai_penalty': round(ai_penalty, 4),
        },
        'method': {
            'retrieval': 'semantic_vector + lexical_overlap',
            'embedding_model': semantic_index['model_name'],
            'semantic_top_k': top_k,
            'ai_source': ai_source,
        },
        'progress_bound': {
            'max_order': max_order,
        },
        'risk_flags': build_risk_flags(
            support_coverage=support_coverage,
            scope_alignment=scope_alignment,
            answer_specificity=answer_specificity,
            evidence_consistency=evidence_consistency,
            ai_rate=ai_rate,
            top_future=top_future,
        ),
        'supporting_chunks': [serialize_ranked_chunk(item) for item in top_support],
        'future_reference_chunks': [serialize_ranked_chunk(item) for item in top_future],
        'answer_preview': shorten(answer_text, 300),
        'question_preview': shorten(question_text or '', 180) if question_text else None,
    }


def score_chunks(
    *,
    query_text: str,
    query_tokens: set[str],
    chunks: list[dict],
    semantic_index: dict[str, Any],
    top_k: int,
) -> list[dict[str, Any]]:
    if not chunks:
        return []

    allowed_chunk_ids = {chunk['chunk_id'] for chunk in chunks}
    semantic_results = semantic_search(
        query_text=query_text,
        index=semantic_index,
        top_k=min(max(top_k, 1) * 3, len(semantic_index['chunks'])),
    )

    ranked: list[dict[str, Any]] = []
    for item in semantic_results:
        chunk = item['chunk']
        if chunk['chunk_id'] not in allowed_chunk_ids:
            continue

        chunk_tokens = tokenize_text(chunk['text'])
        overlap = sorted(query_tokens & chunk_tokens)
        lexical_score = 0.0
        if overlap:
            lexical_score = len(overlap) / math.sqrt(max(len(query_tokens), 1) * max(len(chunk_tokens), 1))

        semantic_score = normalize_semantic_score(item['semantic_score'])
        combined_score = 0.7 * semantic_score + 0.3 * clamp(lexical_score * 8.0, 0.0, 1.0)

        ranked.append(
            {
                'chunk': chunk,
                'semantic_score': semantic_score,
                'lexical_score': lexical_score,
                'combined_score': combined_score,
                'overlap': overlap[:20],
            }
        )

    ranked.sort(
        key=lambda item: (
            item['combined_score'],
            item['semantic_score'],
            item['chunk']['order'],
        ),
        reverse=True,
    )
    return ranked[:top_k]


def semantic_search(*, query_text: str, index: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    if not query_text.strip():
        return []

    try:
        import numpy as np
    except ImportError as exc:
        raise AssessmentResourceError('numpy is required for assessment semantic search.') from exc

    query_embedding = encode_texts(
        texts=[query_text],
        model_name=index['model_name'],
        is_query=True,
    )[0]
    scores = index['embeddings'] @ query_embedding
    ranked_indices = np.argsort(scores)[::-1][:top_k]

    results: list[dict[str, Any]] = []
    for idx in ranked_indices:
        chunk = index['chunks'][int(idx)]
        results.append(
            {
                'chunk': chunk,
                'semantic_score': float(scores[int(idx)]),
            }
        )
    return results


def encode_texts(*, texts: list[str], model_name: str, is_query: bool):
    tokenizer, model, device = load_embedding_model(model_name)
    batch_size = 16
    vectors = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        normalized_batch = [normalize_embedding_input(text, is_query=is_query) for text in batch]
        encoded = tokenizer(
            normalized_batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors='pt',
        ).to(device)

        import torch

        with torch.no_grad():
            outputs = model(**encoded)
            pooled = mean_pooling(outputs.last_hidden_state, encoded['attention_mask'])
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors.append(pooled.cpu().numpy())

    import numpy as np

    return np.vstack(vectors)


@lru_cache(maxsize=2)
def load_embedding_model(model_name: str):
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise AssessmentResourceError('torch and transformers are required for assessment embeddings.') from exc

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    model.eval()
    return tokenizer, model, device


def mean_pooling(last_hidden_state, attention_mask):
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    masked = last_hidden_state * mask
    summed = masked.sum(dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def normalize_embedding_input(text: str, *, is_query: bool) -> str:
    text = ' '.join((text or '').split()).strip()
    if not text:
        return ''
    if is_query:
        return f'{QUERY_INSTRUCTION}{text}'
    return text


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open('r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_semantic_score(score: float) -> float:
    return clamp((score + 1.0) / 2.0, 0.0, 1.0)


def tokenize_text(text: str) -> set[str]:
    lowered = (text or '').lower()
    tokens: set[str] = set()

    for token in ENGLISH_TOKEN_RE.findall(lowered):
        if len(token) >= 2:
            tokens.add(token)

    for segment in CHINESE_SEGMENT_RE.findall(text or ''):
        segment = segment.strip()
        if not segment:
            continue
        if len(segment) <= 8 and segment not in CHINESE_STOPWORDS:
            tokens.add(segment)
        max_n = min(4, len(segment))
        for n in range(2, max_n + 1):
            for index in range(0, len(segment) - n + 1):
                gram = segment[index:index + n]
                if gram not in CHINESE_STOPWORDS:
                    tokens.add(gram)
    return tokens


def compute_support_coverage(answer_tokens: set[str], ranked_chunks: list[dict]) -> float:
    if not answer_tokens or not ranked_chunks:
        return 0.0
    matched: set[str] = set()
    for item in ranked_chunks:
        matched.update(item['overlap'])
    return len(matched & answer_tokens) / max(len(answer_tokens), 1)


def compute_support_density(ranked_chunks: list[dict]) -> float:
    if not ranked_chunks:
        return 0.0
    weighted = 0.0
    total_weight = 0.0
    for index, item in enumerate(ranked_chunks[:3], start=1):
        weight = 1 / index
        weighted += item['combined_score'] * weight
        total_weight += weight
    return clamp(weighted / max(total_weight, 1e-9), 0.0, 1.0)


def compute_scope_alignment(in_scope_ranked: list[dict], future_ranked: list[dict]) -> float:
    best_in_scope = in_scope_ranked[0]['combined_score'] if in_scope_ranked else 0.0
    best_future = future_ranked[0]['combined_score'] if future_ranked else 0.0
    if best_in_scope <= 0 and best_future <= 0:
        return 0.2
    if best_future <= best_in_scope:
        return 1.0
    ratio = best_future / max(best_in_scope, 0.0001)
    return clamp(1.12 - 0.32 * ratio, 0.0, 1.0)


def compute_answer_specificity(answer_text: str, answer_tokens: set[str]) -> float:
    length_score = clamp(len(answer_text.strip()) / 220.0, 0.0, 1.0)
    token_score = clamp(len(answer_tokens) / 35.0, 0.0, 1.0)
    sentence_count = len([part for part in SENTENCE_SPLIT_RE.split(answer_text) if part.strip()])
    structure_score = clamp(sentence_count / 4.0, 0.0, 1.0)
    return 0.45 * length_score + 0.35 * token_score + 0.2 * structure_score


def compute_evidence_consistency(ranked_chunks: list[dict]) -> float:
    if not ranked_chunks:
        return 0.0
    semantic_avg = sum(item['semantic_score'] for item in ranked_chunks[:3]) / min(len(ranked_chunks), 3)
    overlap_non_empty = sum(1 for item in ranked_chunks[:3] if item['overlap'])
    overlap_ratio = overlap_non_empty / min(len(ranked_chunks), 3)
    return clamp(0.65 * semantic_avg + 0.35 * overlap_ratio, 0.0, 1.0)


def build_risk_flags(
    *,
    support_coverage: float,
    scope_alignment: float,
    answer_specificity: float,
    evidence_consistency: float,
    ai_rate: float | None,
    top_future: list[dict],
) -> list[str]:
    flags: list[str] = []
    if support_coverage < 0.2:
        flags.append('教材支撑较弱')
    elif support_coverage < 0.4:
        flags.append('教材支撑一般')

    if evidence_consistency < 0.45:
        flags.append('证据一致性不足')

    if scope_alignment < 0.45 and top_future and top_future[0]['combined_score'] > 0:
        flags.append('疑似超出当前学习进度')

    if answer_specificity < 0.35:
        flags.append('答案过短或信息密度不足')

    if ai_rate is not None:
        if ai_rate >= 0.8:
            flags.append('AI生成概率较高')
        elif ai_rate >= 0.5:
            flags.append('存在较明显AI参与迹象')

    if not flags:
        flags.append('暂无明显风险')
    return flags


def classify_score(score: float) -> str:
    if score >= 0.8:
        return '高可信'
    if score >= 0.6:
        return '中等可信'
    if score >= 0.4:
        return '存疑'
    return '低可信'


def serialize_ranked_chunk(item: dict[str, Any]) -> dict[str, Any]:
    chunk = item['chunk']
    return {
        'chunk_id': chunk['chunk_id'],
        'order': chunk['order'],
        'chapter': chunk.get('chapter'),
        'section': chunk.get('section'),
        'topic': chunk.get('topic'),
        'page_start': chunk['page_start'],
        'page_end': chunk['page_end'],
        'semantic_score': round(item['semantic_score'], 4),
        'lexical_score': round(item['lexical_score'], 4),
        'combined_score': round(item['combined_score'], 4),
        'overlap': item['overlap'],
        'snippet': shorten(chunk['text'], 280),
    }


def shorten(text: str, limit: int) -> str:
    text = re.sub(r'\s+', ' ', text or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '...'


def build_teacher_recommendation(result: dict[str, Any]) -> str:
    if result['label'] == '高可信':
        return '建议将该答案视为教材范围内的高可信回答，可重点核查表述是否完整、是否有少量措辞偏差。'
    if result['label'] == '中等可信':
        return '建议人工复核前 3 个支撑教材片段，确认答案是否准确复述了课本内容，并检查是否存在少量超纲扩展。'
    if result['label'] == '存疑':
        return '建议结合学生当前学习进度和课堂表现复核该答案，重点检查答案中的关键术语是否来自当前章节。'
    return '建议重点人工核查。当前答案的教材支撑度偏弱，或 AI 参与迹象较高，不能直接作为高可信学习结果使用。'


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
