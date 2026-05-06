from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderRequirement:
    name: str
    category: str
    required_for: str
    paid: bool
    required_env_vars: tuple[str, ...]
    any_env_var_groups: tuple[tuple[str, ...], ...] = ()
    alternative_env_var_groups: tuple[tuple[str, ...], ...] = ()
    optional_env_vars: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ProviderReadinessItem:
    name: str
    category: str
    required_for: str
    paid: bool
    configured: bool
    configured_env_vars: tuple[str, ...]
    missing_env_vars: tuple[str, ...]
    optional_env_vars: tuple[str, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class ProviderReadinessResult:
    status: str
    providers_total: int
    configured_providers: int
    missing_providers: int
    paid_provider_blockers: tuple[str, ...]
    providers: tuple[ProviderReadinessItem, ...]


PROVIDER_REQUIREMENTS: tuple[ProviderRequirement, ...] = (
    ProviderRequirement(
        name="PostgreSQL staging database",
        category="database",
        required_for="staging persistence",
        paid=False,
        required_env_vars=("LEGAL_ENGINE_DATABASE_URL",),
        notes="SQLite remains the local default; staging should provide a PostgreSQL DSN.",
    ),
    ProviderRequirement(
        name="Redis queue",
        category="queue",
        required_for="asynchronous production jobs",
        paid=False,
        required_env_vars=("REDIS_URL",),
    ),
    ProviderRequirement(
        name="Vector store",
        category="vector_store",
        required_for="external vector retrieval",
        paid=False,
        required_env_vars=(),
        alternative_env_var_groups=(("PINECONE_API_KEY", "PINECONE_INDEX_NAME"), ("QDRANT_URL",)),
        optional_env_vars=("QDRANT_API_KEY",),
        notes="Configure Pinecone or Qdrant for provider-backed retrieval.",
    ),
    ProviderRequirement(
        name="OpenAI embeddings",
        category="embeddings",
        required_for="external multilingual embeddings",
        paid=True,
        required_env_vars=("OPENAI_API_KEY",),
    ),
    ProviderRequirement(
        name="Cohere rerank",
        category="reranker",
        required_for="premium reranking before generation",
        paid=True,
        required_env_vars=("COHERE_API_KEY",),
    ),
    ProviderRequirement(
        name="LLM generator",
        category="llm",
        required_for="non-deterministic answer generation",
        paid=True,
        required_env_vars=(),
        any_env_var_groups=(("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),),
        notes="Production should choose a generator model and keep the validator independent.",
    ),
    ProviderRequirement(
        name="LLM validator",
        category="validator",
        required_for="independent answer validation",
        paid=True,
        required_env_vars=(),
        any_env_var_groups=(("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),),
        notes="Production should use an independent model/provider from the generator when possible.",
    ),
    ProviderRequirement(
        name="Tavily discovery",
        category="discovery",
        required_for="official-source URL discovery",
        paid=True,
        required_env_vars=("TAVILY_API_KEY",),
    ),
    ProviderRequirement(
        name="Firecrawl crawling",
        category="crawler",
        required_for="robust external crawling",
        paid=True,
        required_env_vars=("FIRECRAWL_API_KEY",),
    ),
    ProviderRequirement(
        name="Langfuse observability",
        category="observability",
        required_for="traces, datasets, latency and cost monitoring",
        paid=False,
        required_env_vars=("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"),
        optional_env_vars=("LANGFUSE_HOST",),
    ),
    ProviderRequirement(
        name="n8n automation runtime",
        category="automation",
        required_for="scheduled operational workflows",
        paid=False,
        required_env_vars=("LEGAL_ENGINE_BASE_URL", "LEGAL_ENGINE_ADMIN_TOKEN"),
        notes="Workflow exports are locally validated; this check only verifies runtime environment wiring.",
    ),
)


def get_provider_readiness(environ: Mapping[str, str] | None = None) -> ProviderReadinessResult:
    environment = os.environ if environ is None else environ
    providers = tuple(_provider_item(requirement, environment) for requirement in PROVIDER_REQUIREMENTS)
    configured_providers = sum(1 for provider in providers if provider.configured)
    missing_providers = len(providers) - configured_providers
    paid_provider_blockers = tuple(provider.name for provider in providers if provider.paid and not provider.configured)
    return ProviderReadinessResult(
        status="ready" if missing_providers == 0 else "blocked",
        providers_total=len(providers),
        configured_providers=configured_providers,
        missing_providers=missing_providers,
        paid_provider_blockers=paid_provider_blockers,
        providers=providers,
    )


def _provider_item(requirement: ProviderRequirement, environment: Mapping[str, str]) -> ProviderReadinessItem:
    configured_env_vars = tuple(
        env_var for env_var in _known_env_vars(requirement) if _has_value(environment.get(env_var))
    )
    missing_required_vars = [
        env_var for env_var in requirement.required_env_vars if not _has_value(environment.get(env_var))
    ]
    missing_any_groups = [
        " or ".join(group)
        for group in requirement.any_env_var_groups
        if not any(_has_value(environment.get(env_var)) for env_var in group)
    ]
    missing_alternatives: list[str] = []
    if requirement.alternative_env_var_groups and not any(
        all(_has_value(environment.get(env_var)) for env_var in group)
        for group in requirement.alternative_env_var_groups
    ):
        missing_alternatives.append(
            " or ".join(" and ".join(group) for group in requirement.alternative_env_var_groups)
        )
    missing_env_vars = tuple(missing_required_vars + missing_any_groups + missing_alternatives)
    return ProviderReadinessItem(
        name=requirement.name,
        category=requirement.category,
        required_for=requirement.required_for,
        paid=requirement.paid,
        configured=not missing_env_vars,
        configured_env_vars=configured_env_vars,
        missing_env_vars=missing_env_vars,
        optional_env_vars=requirement.optional_env_vars,
        notes=requirement.notes,
    )


def _known_env_vars(requirement: ProviderRequirement) -> tuple[str, ...]:
    any_group_vars = tuple(env_var for group in requirement.any_env_var_groups for env_var in group)
    alternative_group_vars = tuple(env_var for group in requirement.alternative_env_var_groups for env_var in group)
    return tuple(
        dict.fromkeys(
            requirement.required_env_vars + any_group_vars + alternative_group_vars + requirement.optional_env_vars
        )
    )


def _has_value(value: str | None) -> bool:
    return bool(value and value.strip())
