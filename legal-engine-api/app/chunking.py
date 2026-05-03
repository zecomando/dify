from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from app.repository import LegalChunkRecord

ARTICLE_HEADING_PATTERN = re.compile(r"^\s*(Artigo|Article)\s+[\w.ºº-]+", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"\d+(?:\.?[ºª])?|\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class TextSection:
    heading: str | None
    text: str


def chunk_text(
    raw_text: str,
    *,
    document_id: str,
    created_at: str,
    max_tokens: int = 180,
) -> tuple[LegalChunkRecord, ...]:
    cleaned_text = raw_text.strip()
    if not cleaned_text:
        return ()

    chunks: list[LegalChunkRecord] = []
    sequence = 1
    for section in _split_sections(cleaned_text):
        chunk_type = "article" if section.heading else "paragraph"
        structural_path = section.heading
        citation_label = section.heading or f"Chunk {sequence}"
        for text_content in _pack_text(section.text, max_tokens=max_tokens):
            chunks.append(
                LegalChunkRecord(
                    id=str(uuid5(NAMESPACE_URL, f"{document_id}:{sequence}:{text_content}")),
                    document_id=document_id,
                    chunk_type=chunk_type,
                    structural_path=structural_path,
                    citation_label=citation_label,
                    text_content=text_content,
                    token_count=count_tokens(text_content),
                    created_at=created_at,
                )
            )
            sequence += 1
    return tuple(chunks)


def count_tokens(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_sections(text: str) -> tuple[TextSection, ...]:
    sections: list[TextSection] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        normalized_line = line.strip()
        if ARTICLE_HEADING_PATTERN.match(normalized_line) and current_lines:
            sections.append(TextSection(heading=current_heading, text="\n".join(current_lines).strip()))
            current_heading = normalize_text(normalized_line)
            current_lines = [normalized_line]
            continue
        if ARTICLE_HEADING_PATTERN.match(normalized_line) and not current_lines:
            current_heading = normalize_text(normalized_line)
        current_lines.append(line)

    if current_lines:
        sections.append(TextSection(heading=current_heading, text="\n".join(current_lines).strip()))

    return tuple(section for section in sections if section.text)


def _pack_text(text: str, *, max_tokens: int) -> tuple[str, ...]:
    paragraphs = [normalize_text(paragraph) for paragraph in re.split(r"\n\s*\n", text) if normalize_text(paragraph)]
    if not paragraphs:
        normalized_text = normalize_text(text)
        return (normalized_text,) if normalized_text else ()

    packed: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        if paragraph_tokens > max_tokens:
            if current:
                packed.append("\n\n".join(current))
                current = []
                current_tokens = 0
            packed.extend(_split_long_paragraph(paragraph, max_tokens=max_tokens))
            continue
        if current and current_tokens + paragraph_tokens > max_tokens:
            packed.append("\n\n".join(current))
            current = [paragraph]
            current_tokens = paragraph_tokens
            continue
        current.append(paragraph)
        current_tokens += paragraph_tokens

    if current:
        packed.append("\n\n".join(current))

    return tuple(packed)


def _split_long_paragraph(paragraph: str, *, max_tokens: int) -> tuple[str, ...]:
    words = paragraph.split()
    return tuple(" ".join(words[index : index + max_tokens]) for index in range(0, len(words), max_tokens))
