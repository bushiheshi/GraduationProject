import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十]+章\s*.+$")
SECTION_RE = re.compile(r"^第[一二三四五六七八九十]+节\s*.+$")
PROJECT_RE = re.compile(r"^项目主题\s*.+$")
STRUCTURE_RE = re.compile(r"^本章知识结构.*$")
PAGE_ARTIFACT_RE = re.compile(r"/G[0-9A-F]{2}")
NOISE_REPLACEMENTS = (
    ("书书书", ""),
    ("SNN^Y'[fQúrHy>", ""),
    ("\x0c", "\n"),
)


@dataclass
class Chunk:
    chunk_id: str
    order: int
    chapter: str | None
    section: str | None
    topic: str | None
    page_start: int
    page_end: int
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a textbook PDF into an ordered local knowledge base.")
    parser.add_argument(
        "--pdf",
        default=None,
        help="Path to textbook PDF. If omitted, use the first PDF in the project root.",
    )
    parser.add_argument(
        "--out-dir",
        default="test/textbook_kb",
        help="Output directory for extracted pages and chunks.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=900,
        help="Approximate max characters per chunk.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    pdf_path = resolve_pdf_path(root, args.pdf)
    out_dir = (root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = extract_pages(pdf_path)
    chunks, outline = build_ordered_chunks(pages, chunk_size=args.chunk_size)

    write_json(out_dir / "source_pdf.json", {"pdf_path": str(pdf_path), "page_count": len(pages)})
    write_json(out_dir / "outline.json", outline)
    write_jsonl(out_dir / "pages.jsonl", pages)
    write_jsonl(out_dir / "kb_chunks.jsonl", [asdict(chunk) for chunk in chunks])
    write_markdown_preview(out_dir / "preview.md", pdf_path=pdf_path, outline=outline, chunks=chunks)

    print(f"PDF: {pdf_path}")
    print(f"Pages extracted: {len(pages)}")
    print(f"Chunks built: {len(chunks)}")
    print(f"Output directory: {out_dir}")
    return 0


def resolve_pdf_path(root: Path, explicit_path: str | None) -> Path:
    if explicit_path:
        pdf_path = Path(explicit_path)
        if not pdf_path.is_absolute():
            pdf_path = (root / pdf_path).resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        return pdf_path

    pdfs = sorted(root.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError("No PDF found in project root.")
    return pdfs[0]


def extract_pages(pdf_path: Path) -> list[dict]:
    reader = PdfReader(str(pdf_path))
    pages: list[dict] = []

    current_chapter: str | None = None
    current_section: str | None = None
    current_topic: str | None = None

    for page_index, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        clean_text = normalize_text(raw_text)
        headings = detect_headings(clean_text)
        page_type = classify_page(clean_text, page_index=page_index)

        if page_type == "content" and headings["chapter"]:
            current_chapter = headings["chapter"]
            current_section = None
            current_topic = None
        if page_type == "content" and headings["section"]:
            current_section = headings["section"]
        if page_type == "content" and headings["topic"]:
            current_topic = headings["topic"]

        pages.append(
            {
                "page": page_index,
                "page_type": page_type,
                "chapter": current_chapter,
                "section": current_section,
                "topic": current_topic,
                "detected_headings": headings,
                "text": clean_text,
            }
        )

    return pages


def normalize_text(text: str) -> str:
    normalized = text
    for src, target in NOISE_REPLACEMENTS:
        normalized = normalized.replace(src, target)
    normalized = PAGE_ARTIFACT_RE.sub("", normalized)
    normalized = normalized.replace("", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    normalized = re.sub(r"(?<=\d) (?=\d)", "", normalized)
    return normalized.strip()


def detect_headings(text: str) -> dict[str, str | None]:
    chapter = None
    section = None
    topic = None

    for raw_line in text.splitlines():
        line = normalize_heading(raw_line)
        if not line:
            continue
        if chapter is None and CHAPTER_RE.match(line) and len(line) <= 24:
            chapter = line
            continue
        if section is None and SECTION_RE.match(line) and len(line) <= 28:
            section = line
            continue
        if topic is None and PROJECT_RE.match(line) and len(line) <= 28:
            topic = line
            continue
        if topic is None and STRUCTURE_RE.match(line) and len(line) <= 24:
            topic = line

    return {
        "chapter": chapter,
        "section": section,
        "topic": topic,
    }


def normalize_heading(value: str) -> str:
    value = re.sub(r"\.\.\.\s*\d+\s*$", "", value)
    value = re.sub(r"…+\s*\d+\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip(" .。")


def classify_page(text: str, *, page_index: int) -> str:
    if not text:
        return "empty"
    if page_index <= 8:
        if "第一章" in text or "第二章" in text or "第三章" in text or "第四章" in text:
            return "toc"
        return "front_matter"
    if "目录" in text or text.count("...") >= 4 or text.count("…") >= 4:
        return "toc"
    if any(marker in text for marker in ("致同学们", "总 主 编", "副总主编", "版权所有")):
        return "front_matter"
    if "第一章" in text or "第二章" in text or "第三章" in text or "第四章" in text:
        return "content"
    if "第一节" in text or "第二节" in text or "第三节" in text:
        return "content"
    return "content"


def build_ordered_chunks(pages: list[dict], *, chunk_size: int) -> tuple[list[Chunk], list[dict]]:
    chunks: list[Chunk] = []
    outline_map: dict[tuple[str | None, str | None], dict] = {}

    buffer: list[str] = []
    buffer_start_page: int | None = None
    chunk_order = 1

    def flush(page_end: int, chapter: str | None, section: str | None, topic: str | None) -> None:
        nonlocal buffer, buffer_start_page, chunk_order
        if not buffer or buffer_start_page is None:
            return
        text = "\n".join(buffer).strip()
        if not text:
            buffer = []
            buffer_start_page = None
            return

        chunk = Chunk(
            chunk_id=f"chunk-{chunk_order:04d}",
            order=chunk_order,
            chapter=chapter,
            section=section,
            topic=topic,
            page_start=buffer_start_page,
            page_end=page_end,
            text=text,
        )
        chunks.append(chunk)
        chunk_order += 1
        buffer = []
        buffer_start_page = None

    for page in pages:
        if page["page_type"] != "content":
            continue

        chapter = page["chapter"]
        section = page["section"]
        topic = page["topic"]
        key = (chapter, section)

        if key not in outline_map:
            outline_map[key] = {
                "chapter": chapter,
                "section": section,
                "first_page": page["page"],
                "last_page": page["page"],
            }
        else:
            outline_map[key]["last_page"] = page["page"]

        paragraphs = split_paragraphs(page["text"])
        for paragraph in paragraphs:
            if not paragraph:
                continue

            projected = len("\n".join(buffer + [paragraph]))
            if buffer and projected > chunk_size:
                flush(page["page"], chapter, section, topic)

            if buffer_start_page is None:
                buffer_start_page = page["page"]
            buffer.append(paragraph)

        flush(page["page"], chapter, section, topic)

    outline = sorted(
        outline_map.values(),
        key=lambda item: (item["first_page"], item["chapter"] or "", item["section"] or ""),
    )
    return chunks, outline


def split_paragraphs(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line and not looks_like_page_header_footer(line)]

    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if is_heading_line(line):
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            paragraphs.append(line)
            continue

        current.append(line)
        if len(" ".join(current)) >= 260:
            paragraphs.append(" ".join(current).strip())
            current = []

    if current:
        paragraphs.append(" ".join(current).strip())
    return paragraphs


def is_heading_line(line: str) -> bool:
    return bool(CHAPTER_RE.fullmatch(line) or SECTION_RE.fullmatch(line) or PROJECT_RE.fullmatch(line))


def looks_like_page_header_footer(line: str) -> bool:
    if len(line) <= 2:
        return True
    if re.fullmatch(r"\d+", line):
        return True
    if line in {"数据与计算", "致同学们"}:
        return True
    return False


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_markdown_preview(path: Path, *, pdf_path: Path, outline: list[dict], chunks: list[Chunk]) -> None:
    lines = [
        f"# 教材知识库预览",
        "",
        f"- PDF: `{pdf_path.name}`",
        f"- Chunks: `{len(chunks)}`",
        "",
        "## 目录概要",
        "",
    ]

    for item in outline[:30]:
        title = " / ".join(part for part in [item["chapter"], item["section"]] if part)
        title = title or "未识别章节"
        lines.append(f"- {title} (页 {item['first_page']} - {item['last_page']})")

    lines.extend(["", "## 前 10 个 Chunk", ""])
    for chunk in chunks[:10]:
        title = " / ".join(part for part in [chunk.chapter, chunk.section, chunk.topic] if part) or "未识别标题"
        lines.append(f"### {chunk.chunk_id} | {title} | 页 {chunk.page_start}-{chunk.page_end}")
        lines.append("")
        lines.append(chunk.text[:500] + ("..." if len(chunk.text) > 500 else ""))
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
