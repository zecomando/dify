from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field


class SourcePolicyStatus(StrEnum):
    OFFICIAL_AUTHORITY = "official_authority"
    DISCOVERY_ONLY = "discovery_only"
    BLOCKED = "blocked"
    UNKNOWN_DOMAIN = "unknown_domain"
    INVALID_URL = "invalid_url"


class SourcePolicyAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jurisdiction: str
    source: str
    domain: str
    allowed_document_types: list[str]
    may_ground_answer: bool
    requires_consolidation_warning: bool
    required_metadata: list[str]
    required_identifiers_any: list[str]


class SourcePolicyCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)


class SourcePolicyCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SourcePolicyStatus
    domain: str | None
    may_ground_answer: bool
    reason: str
    authority: SourcePolicyAuthority | None = None


@dataclass(frozen=True, slots=True)
class AuthorityRule:
    jurisdiction: str
    source: str
    domain: str
    allowed_document_types: tuple[str, ...]
    may_ground_answer: bool
    requires_consolidation_warning: bool
    required_metadata: tuple[str, ...]
    required_identifiers_any: tuple[str, ...]

    def to_response_model(self) -> SourcePolicyAuthority:
        return SourcePolicyAuthority(
            jurisdiction=self.jurisdiction,
            source=self.source,
            domain=self.domain,
            allowed_document_types=list(self.allowed_document_types),
            may_ground_answer=self.may_ground_answer,
            requires_consolidation_warning=self.requires_consolidation_warning,
            required_metadata=list(self.required_metadata),
            required_identifiers_any=list(self.required_identifiers_any),
        )


class SourcePolicy:
    version: int
    name: str
    authorities: tuple[AuthorityRule, ...]
    discovery_only_domains: tuple[str, ...]
    blocked_domains: tuple[str, ...]

    def __init__(
        self,
        *,
        version: int,
        name: str,
        authorities: tuple[AuthorityRule, ...],
        discovery_only_domains: tuple[str, ...],
        blocked_domains: tuple[str, ...],
    ) -> None:
        self.version = version
        self.name = name
        self.authorities = authorities
        self.discovery_only_domains = discovery_only_domains
        self.blocked_domains = blocked_domains

    @classmethod
    def from_file(cls, path: Path) -> SourcePolicy:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = _as_mapping(raw)
        authorities = _load_authorities(data.get("answer_authorities"))
        discovery_only_domains = _load_domain_list(data.get("discovery_only"))
        blocked_domains = _load_string_list(data.get("blocked_as_authority"))
        return cls(
            version=_as_int(data.get("version"), default=1),
            name=_as_str(data.get("name"), default="legal_ai_source_policy"),
            authorities=authorities,
            discovery_only_domains=discovery_only_domains,
            blocked_domains=blocked_domains,
        )

    def check_url(self, url: str) -> SourcePolicyCheckResult:
        domain = normalize_url_domain(url)
        if domain is None:
            return SourcePolicyCheckResult(
                status=SourcePolicyStatus.INVALID_URL,
                domain=None,
                may_ground_answer=False,
                reason="URL must be absolute and use http or https.",
            )

        blocked_domain = find_matching_domain(domain, self.blocked_domains)
        if blocked_domain is not None:
            return SourcePolicyCheckResult(
                status=SourcePolicyStatus.BLOCKED,
                domain=domain,
                may_ground_answer=False,
                reason=f"Domain matches blocked authority rule: {blocked_domain}.",
            )

        authority = self.find_authority(domain)
        if authority is not None:
            return SourcePolicyCheckResult(
                status=SourcePolicyStatus.OFFICIAL_AUTHORITY,
                domain=domain,
                may_ground_answer=authority.may_ground_answer,
                reason=f"Domain matches official source policy authority: {authority.domain}.",
                authority=authority.to_response_model(),
            )

        discovery_domain = find_matching_domain(domain, self.discovery_only_domains)
        if discovery_domain is not None:
            return SourcePolicyCheckResult(
                status=SourcePolicyStatus.DISCOVERY_ONLY,
                domain=domain,
                may_ground_answer=False,
                reason=f"Domain is discovery-only and cannot ground final legal conclusions: {discovery_domain}.",
            )

        return SourcePolicyCheckResult(
            status=SourcePolicyStatus.UNKNOWN_DOMAIN,
            domain=domain,
            may_ground_answer=False,
            reason="Domain is not approved as an authority by the source policy.",
        )

    def find_authority(self, domain: str) -> AuthorityRule | None:
        matching_authorities = [authority for authority in self.authorities if domain_matches(domain, authority.domain)]
        if not matching_authorities:
            return None
        return max(
            matching_authorities,
            key=lambda authority: len(authority.domain.removeprefix("www.").lower()),
        )


def get_default_source_policy_path() -> Path:
    env_path = os.environ.get("LEGAL_SOURCE_POLICY_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def normalize_url_domain(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname.removeprefix("www.").lower()


def domain_matches(domain: str, policy_domain: str) -> bool:
    normalized_policy_domain = policy_domain.removeprefix("www.").lower()
    return domain == normalized_policy_domain or domain.endswith(f".{normalized_policy_domain}")


def find_matching_domain(domain: str, policy_domains: Sequence[str]) -> str | None:
    for policy_domain in policy_domains:
        if domain_matches(domain, policy_domain):
            return policy_domain
    return None


def validate_source_requirements(
    authority: SourcePolicyAuthority,
    *,
    document_type: str | None,
    source_url: str,
    raw_text: str = "",
    legal_metadata: dict[str, str] | None = None,
) -> list[str]:
    violations: list[str] = []
    normalized_metadata = _normalize_metadata(legal_metadata or {})
    if document_type is not None and document_type not in authority.allowed_document_types:
        violations.append(f"Document type {document_type} is not allowed for {authority.source}.")

    missing_metadata = [
        required_field
        for required_field in authority.required_metadata
        if not _has_required_metadata(required_field, normalized_metadata, source_url)
    ]
    if missing_metadata:
        violations.append(f"Missing required metadata for {authority.source}: {', '.join(missing_metadata)}.")

    if authority.required_identifiers_any and not any(
        _has_required_identifier(identifier, normalized_metadata, source_url, raw_text)
        for identifier in authority.required_identifiers_any
    ):
        violations.append(
            f"Missing at least one required identifier for {authority.source}: "
            f"{', '.join(authority.required_identifiers_any)}."
        )
    return violations


def _load_authorities(value: object) -> tuple[AuthorityRule, ...]:
    jurisdictions = _as_mapping(value)
    rules: list[AuthorityRule] = []
    for jurisdiction, entries_value in jurisdictions.items():
        jurisdiction_name = str(jurisdiction)
        for entry_value in _as_sequence(entries_value):
            entry = _as_mapping(entry_value)
            rules.append(
                AuthorityRule(
                    jurisdiction=jurisdiction_name,
                    source=_as_str(entry.get("source"), default="UNKNOWN"),
                    domain=_as_str(entry.get("domain"), default=""),
                    allowed_document_types=_load_string_list(entry.get("allowed_document_types")),
                    may_ground_answer=_as_bool(entry.get("may_ground_answer"), default=False),
                    requires_consolidation_warning=_as_bool(
                        entry.get("requires_consolidation_warning"),
                        default=False,
                    ),
                    required_metadata=_load_string_list(entry.get("required_metadata")),
                    required_identifiers_any=_load_string_list(entry.get("required_identifiers_any")),
                )
            )
    return tuple(rule for rule in rules if rule.domain)


def _normalize_metadata(legal_metadata: dict[str, str]) -> dict[str, str]:
    return {
        key.strip().lower(): value.strip() for key, value in legal_metadata.items() if key.strip() and value.strip()
    }


def _has_required_metadata(required_field: str, legal_metadata: dict[str, str], source_url: str) -> bool:
    normalized_field = required_field.lower()
    if normalized_field == "source_url" and source_url.strip():
        return True
    return bool(legal_metadata.get(normalized_field))


def _has_required_identifier(
    required_identifier: str,
    legal_metadata: dict[str, str],
    source_url: str,
    raw_text: str,
) -> bool:
    normalized_identifier = required_identifier.lower()
    if legal_metadata.get(normalized_identifier):
        return True
    haystack = f"{source_url}\n{raw_text}\n{' '.join(legal_metadata.values())}".lower()
    return bool(re.search(rf"(?:^|[^a-z0-9]){re.escape(normalized_identifier)}(?::|=|/)", haystack))


def _load_domain_list(value: object) -> tuple[str, ...]:
    domains: list[str] = []
    for entry_value in _as_sequence(value):
        if isinstance(entry_value, Mapping):
            domain = entry_value.get("domain")
            if isinstance(domain, str):
                domains.append(domain)
    return tuple(domains)


def _load_string_list(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _as_sequence(value) if isinstance(item, str))


def _as_mapping(value: object) -> Mapping[object, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    return ()


def _as_str(value: object, *, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _as_int(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    return default


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default
