from app.chunking import chunk_text, count_tokens, normalize_text


def test_chunk_text_splits_articles_into_stable_chunks():
    raw_text = """
Artigo 1.º
O contrato deve ser cumprido pontualmente.

Artigo 2.º
A responsabilidade civil depende dos pressupostos legais.
"""

    chunks = chunk_text(raw_text, document_id="doc-1", created_at="2026-01-01T00:00:00+00:00")

    assert len(chunks) == 2
    assert chunks[0].chunk_type == "article"
    assert chunks[0].citation_label == "Artigo 1.º"
    assert "contrato" in chunks[0].text_content
    assert chunks[1].citation_label == "Artigo 2.º"
    assert "responsabilidade civil" in chunks[1].text_content


def test_chunk_text_returns_empty_tuple_for_blank_text():
    chunks = chunk_text("   ", document_id="doc-1", created_at="2026-01-01T00:00:00+00:00")

    assert chunks == ()


def test_chunk_text_splits_long_paragraph_by_max_tokens():
    raw_text = " ".join(f"palavra{index}" for index in range(25))

    chunks = chunk_text(raw_text, document_id="doc-1", created_at="2026-01-01T00:00:00+00:00", max_tokens=10)

    assert len(chunks) == 3
    assert [chunk.token_count for chunk in chunks] == [10, 10, 5]


def test_text_helpers_normalize_and_count_tokens():
    assert normalize_text("  texto\n\tcom   espaços  ") == "texto com espaços"
    assert count_tokens("Contrato civil: artigo 1.º") == 4
