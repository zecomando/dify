from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from app.source_policy import SourcePolicyAuthority, normalize_url_domain


class RemoteFetchError(Exception):
    pass


class PermanentRemoteFetchError(RemoteFetchError):
    pass


@dataclass(frozen=True, slots=True)
class RemoteFetchResult:
    final_url: str
    status_code: int
    content_type: str
    text: str


@dataclass(frozen=True, slots=True)
class ParsedRemoteLegalSource:
    source_url: str
    raw_text: str
    source: str
    jurisdiction: str
    document_type: str
    area: tuple[str, ...]
    legal_metadata: dict[str, str]
    promote_if_valid: bool


class RemoteFetcher(Protocol):
    def fetch(self, url: str) -> RemoteFetchResult: ...


class UrllibRemoteFetcher:
    def __init__(self, *, timeout_seconds: int = 10, max_bytes: int = 2_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def fetch(self, url: str) -> RemoteFetchResult:
        request = Request(
            url,
            headers={
                "User-Agent": "legal-engine-api/0.1 (+https://github.com/langgenius/dify)",
                "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise PermanentRemoteFetchError(f"Remote response exceeded maximum size of {self.max_bytes} bytes.")
                content_type = response.headers.get_content_type()
                if not _is_supported_text_content_type(content_type):
                    raise PermanentRemoteFetchError(f"Unsupported remote content type: {content_type}.")
                charset = response.headers.get_content_charset() or "utf-8"
                return RemoteFetchResult(
                    final_url=response.geturl(),
                    status_code=response.getcode(),
                    content_type=content_type,
                    text=body.decode(charset, errors="replace"),
                )
        except HTTPError as exc:
            if 400 <= exc.code < 500:
                raise PermanentRemoteFetchError(f"Remote fetch failed with HTTP {exc.code}.") from exc
            raise RemoteFetchError(f"Remote fetch failed with HTTP {exc.code}.") from exc
        except URLError as exc:
            raise RemoteFetchError(f"Remote fetch failed: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise RemoteFetchError("Remote fetch timed out.") from exc


def _is_supported_text_content_type(content_type: str) -> bool:
    if content_type.startswith("text/"):
        return True
    return content_type in {"application/xhtml+xml", "application/xml", "application/json"}


def parse_remote_legal_source(
    *,
    source_url: str,
    fetched_text: str,
    authority: SourcePolicyAuthority,
) -> ParsedRemoteLegalSource:
    raw_text = html_to_text(fetched_text)
    if not raw_text:
        raise ValueError("Remote source did not contain extractable text.")

    domain = normalize_url_domain(source_url) or ""
    if authority.source == "EURLEX" or domain_matches_any(domain, ("eur-lex.europa.eu",)):
        return _parse_eurlex(source_url, raw_text, authority)
    if authority.source == "DRE" or domain_matches_any(domain, ("dre.pt", "diariodarepublica.pt")):
        return _parse_dre(source_url, raw_text, authority)
    if authority.source in {
        "DGSI",
        "CSM_JURISPRUDENCE",
        "TRIBUNAL_CONSTITUCIONAL",
        "CURIA",
        "INFOCURIA",
        "HUDOC",
    }:
        return _parse_case_law(source_url, raw_text, authority)
    return ParsedRemoteLegalSource(
        source_url=source_url,
        raw_text=raw_text,
        source=authority.source,
        jurisdiction=authority.jurisdiction,
        document_type=_first_allowed_document_type(authority.allowed_document_types),
        area=(_detect_area(raw_text, default="geral"),),
        legal_metadata={},
        promote_if_valid=False,
    )


def html_to_text(value: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    with_breaks = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr|/h[1-6])\s*/?>", "\n", without_scripts)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", with_breaks)
    unescaped = unescape(without_tags)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in unescaped.splitlines()]
    return "\n".join(line for line in lines if line)


def domain_matches_any(domain: str, policy_domains: Sequence[str]) -> bool:
    return any(domain == policy_domain or domain.endswith(f".{policy_domain}") for policy_domain in policy_domains)


def _parse_dre(source_url: str, raw_text: str, authority: SourcePolicyAuthority) -> ParsedRemoteLegalSource:
    return ParsedRemoteLegalSource(
        source_url=source_url,
        raw_text=raw_text,
        source=authority.source,
        jurisdiction=authority.jurisdiction,
        document_type=_dre_document_type(source_url, raw_text, authority.allowed_document_types),
        area=(_detect_area(raw_text, default="geral"),),
        legal_metadata=_dre_metadata(source_url, raw_text),
        promote_if_valid=True,
    )


def _parse_eurlex(source_url: str, raw_text: str, authority: SourcePolicyAuthority) -> ParsedRemoteLegalSource:
    legal_metadata = _eurlex_metadata(source_url, raw_text)
    return ParsedRemoteLegalSource(
        source_url=source_url,
        raw_text=raw_text,
        source=authority.source,
        jurisdiction=authority.jurisdiction,
        document_type=_eurlex_document_type(legal_metadata, authority.allowed_document_types),
        area=(_detect_area(raw_text, default="uniao_europeia"),),
        legal_metadata=legal_metadata,
        promote_if_valid=True,
    )


def _parse_case_law(source_url: str, raw_text: str, authority: SourcePolicyAuthority) -> ParsedRemoteLegalSource:
    return ParsedRemoteLegalSource(
        source_url=source_url,
        raw_text=raw_text,
        source=authority.source,
        jurisdiction=authority.jurisdiction,
        document_type="case_law"
        if "case_law" in authority.allowed_document_types
        else _first_allowed_document_type(authority.allowed_document_types),
        area=(_case_law_area(raw_text, authority.source),),
        legal_metadata=_case_law_metadata(source_url, raw_text, authority.source),
        promote_if_valid=False,
    )


def _dre_document_type(source_url: str, raw_text: str, allowed_document_types: Sequence[str]) -> str:
    normalized = f"{source_url}\n{raw_text}".lower()
    if "aviso" in normalized and "official_notice" in allowed_document_types:
        return "official_notice"
    return (
        "legislation"
        if "legislation" in allowed_document_types
        else _first_allowed_document_type(allowed_document_types)
    )


def _eurlex_document_type(legal_metadata: dict[str, str], allowed_document_types: Sequence[str]) -> str:
    celex = legal_metadata.get("celex", "")
    if celex.startswith("1") and "treaty" in allowed_document_types:
        return "treaty"
    if celex.startswith("5") and "preparatory_act" in allowed_document_types:
        return "preparatory_act"
    return (
        "legislation"
        if "legislation" in allowed_document_types
        else _first_allowed_document_type(allowed_document_types)
    )


def _eurlex_metadata(source_url: str, raw_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    decoded_url = unquote(source_url)
    query_values = parse_qs(urlparse(source_url).query)
    uri_values = query_values.get("uri", ())
    celex = _first_match(
        (
            r"^CELEX:([0-9A-Z]+)$",
            r"[?&]uri=CELEX:([0-9A-Z]+)",
            r"CELEX[:\s]*([0-9][0-9A-Z]{4,})",
        ),
        "\n".join((*uri_values, source_url, decoded_url, raw_text)),
    )
    eli = _first_match((r"ELI[:\s]*([^\s,;]+)", r"/eli/([^\s?#]+)"), f"{source_url}\n{decoded_url}\n{raw_text}")
    if celex:
        metadata["celex"] = celex.upper()
    if eli:
        metadata["eli"] = eli.strip().rstrip(".")
    return metadata


def _dre_metadata(source_url: str, raw_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    decoded_url = unquote(source_url)
    eli = _first_match(
        (
            r"ELI[:\s]*(https?://[^\s,;]+)",
            r"(https?://(?:data\.)?dre\.pt/eli/[^\s,;]+)",
        ),
        f"{source_url}\n{decoded_url}\n{raw_text}",
    )
    diploma = _dre_diploma(raw_text)
    if eli:
        metadata["eli"] = eli.strip().rstrip(".")
    if diploma:
        metadata["diploma"] = diploma
    if source_url:
        metadata["source_url"] = source_url
    return metadata


def _dre_diploma(raw_text: str) -> str | None:
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        normalized = candidate.casefold()
        if normalized.startswith("artigo "):
            continue
        if any(marker in normalized for marker in ("decreto", "lei", "portaria", "despacho", "aviso")):
            return candidate.rstrip(".")
    return None


def _case_law_metadata(source_url: str, raw_text: str, source: str) -> dict[str, str]:
    if source in {"DGSI", "CSM_JURISPRUDENCE", "TRIBUNAL_CONSTITUCIONAL"}:
        return _portuguese_case_law_metadata(source_url, raw_text, source)
    if source in {"CURIA", "INFOCURIA"}:
        return _curia_case_law_metadata(source_url, raw_text)
    if source == "HUDOC":
        return _hudoc_case_law_metadata(source_url, raw_text)
    return {"source_url": source_url} if source_url else {}


def _portuguese_case_law_metadata(source_url: str, raw_text: str, source: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    court = _first_match(
        (
            r"(?m)^Tribunal:[ \t]*([^\n]+)",
            r"(?m)^Acórdão\s+d[oa]\s+((?:Supremo\s+)?Tribunal[^\n]+)",
            r"\b(Supremo Tribunal de Justiça)\b",
        ),
        raw_text,
    )
    process_number = _first_match((r"(?m)^Proc(?:esso)?\.?(?:\s+n[.ººo]*)?:?[ \t]*([A-Z0-9./-]+)",), raw_text)
    decision_date = _first_match(
        (
            r"(?m)^Data(?:\s+do\s+Ac[óo]rdão)?[ \t]*:[ \t]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
            r"(?m)^Data(?:\s+do\s+Ac[óo]rdão)?[ \t]*:[ \t]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})",
        ),
        raw_text,
    )
    if source == "TRIBUNAL_CONSTITUCIONAL" and court is None:
        court = "Tribunal Constitucional"
    if court:
        metadata["court"] = court.strip().rstrip(".")
    if process_number:
        metadata["process_number"] = process_number.strip().rstrip(".")
    if decision_date:
        metadata["decision_date"] = _normalize_iso_date(decision_date)
    if source_url:
        metadata["source_url"] = source_url
    return metadata


def _curia_case_law_metadata(source_url: str, raw_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    court = _first_match((r"(?m)^Court:[ \t]*([^\n]+)", r"\b(Court of Justice)\b"), raw_text)
    case_number = _first_match(("(?m)^Case(?:\\s+No\\.?)?:?[ \\t]*([A-Z][-‐‑‒–—−][0-9]+/[0-9]+)",), raw_text)
    decision_date = _first_match((r"(?m)^Date:[ \t]*([0-9]{4}-[0-9]{2}-[0-9]{2})",), raw_text)
    if court:
        metadata["court"] = court.strip().rstrip(".")
    if case_number:
        metadata["case_number"] = _normalize_case_number(case_number)
    if decision_date:
        metadata["decision_date"] = decision_date
    if source_url:
        metadata["source_url"] = source_url
    return metadata


def _hudoc_case_law_metadata(source_url: str, raw_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    court = _first_match((r"(?m)^Court:[ \t]*([^\n]+)", r"\b(European Court of Human Rights)\b"), raw_text)
    application_number = _first_match((r"(?m)^Application\s+no\.?:?[ \t]*([0-9]+/[0-9]+)",), raw_text)
    decision_date = _first_match((r"(?m)^Date:[ \t]*([0-9]{4}-[0-9]{2}-[0-9]{2})",), raw_text)
    if court:
        metadata["court"] = court.strip().rstrip(".")
    if application_number:
        metadata["application_number"] = application_number.strip().rstrip(".")
    if decision_date:
        metadata["decision_date"] = decision_date
    if source_url:
        metadata["source_url"] = source_url
    return metadata


def _normalize_iso_date(value: str) -> str:
    normalized = value.strip()
    portuguese_date = re.fullmatch(r"([0-9]{2})[/-]([0-9]{2})[/-]([0-9]{4})", normalized)
    if portuguese_date:
        day, month, year = portuguese_date.groups()
        return f"{year}-{month}-{day}"
    return normalized


def _normalize_case_number(value: str) -> str:
    return (
        value.strip().rstrip(".").translate(str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"}))
    )


def _case_law_area(raw_text: str, source: str) -> str:
    if source == "TRIBUNAL_CONSTITUCIONAL":
        return "constitucional"
    return _detect_area(raw_text, default="jurisprudencia")


def _first_match(patterns: Sequence[str], value: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _detect_area(raw_text: str, *, default: str) -> str:
    normalized = raw_text.casefold()
    area_markers = (
        ("proteccao_dados", ("rgpd", "dados pessoais", "proteção de dados", "protecao de dados")),
        (
            "contratacao_publica",
            ("contratação pública", "contratacao publica", "contrato público", "public procurement", "proposta"),
        ),
        ("laboral", ("trabalho", "laboral", "trabalhador", "despedimento")),
        ("fiscal", ("iva", "irc", "irs", "tribut", "fiscal")),
        ("administrativo", ("administrativo", "audiência prévia", "audiencia previa")),
        ("constitucional", ("constitucional", "constituição", "constituicao")),
        ("civil", ("civil", "responsabilidade", "contrato")),
        ("uniao_europeia", ("união europeia", "uniao europeia", "celex", "regulamento", "diretiva")),
    )
    for area, markers in area_markers:
        if any(marker in normalized for marker in markers):
            return area
    return default


def _first_allowed_document_type(allowed_document_types: Sequence[str]) -> str:
    return allowed_document_types[0] if allowed_document_types else "legal_document"
