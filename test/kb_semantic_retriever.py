import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_INDEX_DIRNAME = "vector_index"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关教材内容："


def build_or_load_index(
    *,
    kb_dir: Path,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    index_dir = kb_dir / DEFAULT_INDEX_DIRNAME
    meta_path = index_dir / "index_meta.json"
    embedding_path = index_dir / "chunk_embeddings.npy"

    if not force_rebuild and meta_path.exists() and embedding_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        embeddings = np.load(embedding_path)
        chunks = load_jsonl(kb_dir / "kb_chunks.jsonl")
        return {
            "model_name": metadata["model_name"],
            "embeddings": embeddings,
            "chunks": chunks,
            "index_dir": index_dir,
        }

    index_dir.mkdir(parents=True, exist_ok=True)
    chunks = load_jsonl(kb_dir / "kb_chunks.jsonl")
    texts = [build_chunk_text(chunk) for chunk in chunks]
    embeddings = encode_texts(texts=texts, model_name=model_name, is_query=False)

    metadata = {
        "model_name": model_name,
        "chunk_count": len(chunks),
        "embedding_dim": int(embeddings.shape[1]) if len(embeddings.shape) == 2 else 0,
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    np.save(embedding_path, embeddings)

    return {
        "model_name": model_name,
        "embeddings": embeddings,
        "chunks": chunks,
        "index_dir": index_dir,
    }


def semantic_search(
    *,
    query_text: str,
    index: dict[str, Any],
    top_k: int,
) -> list[dict[str, Any]]:
    if not query_text.strip():
        return []

    query_embedding = encode_texts(
        texts=[query_text],
        model_name=index["model_name"],
        is_query=True,
    )[0]
    chunk_embeddings = index["embeddings"]
    scores = chunk_embeddings @ query_embedding

    ranked_indices = np.argsort(scores)[::-1][:top_k]
    results: list[dict[str, Any]] = []
    for idx in ranked_indices:
        chunk = index["chunks"][int(idx)]
        results.append(
            {
                "chunk": chunk,
                "semantic_score": float(scores[int(idx)]),
            }
        )
    return results


def encode_texts(*, texts: list[str], model_name: str, is_query: bool) -> np.ndarray:
    tokenizer, model, device = load_embedding_model(model_name)
    batch_size = 16
    vectors: list[np.ndarray] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        normalized_batch = [normalize_embedding_input(text, is_query=is_query) for text in batch]
        encoded = tokenizer(
            normalized_batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            outputs = model(**encoded)
            pooled = mean_pooling(outputs.last_hidden_state, encoded["attention_mask"])
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors.append(pooled.cpu().numpy())

    return np.vstack(vectors)


def load_embedding_model(model_name: str):
    if not hasattr(load_embedding_model, "_cache"):
        load_embedding_model._cache = {}

    cache: dict[str, Any] = load_embedding_model._cache
    if model_name in cache:
        return cache[model_name]

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    cache[model_name] = (tokenizer, model, device)
    return cache[model_name]


def mean_pooling(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    masked = last_hidden_state * mask
    summed = masked.sum(dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def normalize_embedding_input(text: str, *, is_query: bool) -> str:
    text = " ".join((text or "").split()).strip()
    if not text:
        return ""
    if is_query:
        return f"{QUERY_INSTRUCTION}{text}"
    return text


def build_chunk_text(chunk: dict[str, Any]) -> str:
    title = " / ".join(
        part for part in [chunk.get("chapter"), chunk.get("section"), chunk.get("topic")] if part
    )
    text = chunk.get("text") or ""
    if title:
        return f"{title}\n{text}"
    return text


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
