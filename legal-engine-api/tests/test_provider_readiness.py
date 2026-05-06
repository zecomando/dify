from app.provider_readiness import get_provider_readiness


def _complete_provider_environment() -> dict[str, str]:
    return {
        "LEGAL_ENGINE_DATABASE_URL": "postgresql://localhost/legal_engine",
        "REDIS_URL": "redis://localhost:6379/0",
        "OPENAI_API_KEY": "openai-secret-value",
        "COHERE_API_KEY": "cohere-secret-value",
        "TAVILY_API_KEY": "tavily-secret-value",
        "FIRECRAWL_API_KEY": "firecrawl-secret-value",
        "LANGFUSE_PUBLIC_KEY": "langfuse-public-value",
        "LANGFUSE_SECRET_KEY": "langfuse-secret-value",
        "LEGAL_ENGINE_BASE_URL": "https://legal-engine.example.test",
        "LEGAL_ENGINE_ADMIN_TOKEN": "admin-secret-value",
    }


def test_provider_readiness_reports_missing_paid_provider_blockers_without_secret_values():
    result = get_provider_readiness({})

    assert result.status == "blocked"
    assert result.missing_providers > 0
    assert "OpenAI embeddings" in result.paid_provider_blockers
    openai_embeddings = next(provider for provider in result.providers if provider.name == "OpenAI embeddings")
    assert openai_embeddings.configured is False
    assert openai_embeddings.missing_env_vars == ("OPENAI_API_KEY",)


def test_provider_readiness_exposes_only_env_var_names_not_values():
    secret_value = "sk-test-secret-value-that-must-not-leak"
    result = get_provider_readiness(
        {
            "OPENAI_API_KEY": secret_value,
            "COHERE_API_KEY": "cohere-secret-value",
            "PINECONE_API_KEY": "pinecone-secret-value",
            "PINECONE_INDEX_NAME": "legal-current",
        }
    )

    serialized = repr(result)
    assert secret_value not in serialized
    assert "cohere-secret-value" not in serialized
    assert "pinecone-secret-value" not in serialized
    openai_embeddings = next(provider for provider in result.providers if provider.name == "OpenAI embeddings")
    assert openai_embeddings.configured is True
    assert openai_embeddings.configured_env_vars == ("OPENAI_API_KEY",)


def test_provider_readiness_accepts_qdrant_as_vector_store_alternative():
    environment = _complete_provider_environment()
    environment["QDRANT_URL"] = "http://localhost:6333"

    result = get_provider_readiness(environment)

    assert result.status == "ready"
    assert "Pinecone vector store" not in result.paid_provider_blockers
    vector_store = next(provider for provider in result.providers if provider.name == "Vector store")
    assert vector_store.configured is True
    assert vector_store.configured_env_vars == ("QDRANT_URL",)


def test_provider_readiness_accepts_pinecone_as_vector_store_alternative():
    environment = _complete_provider_environment()
    environment["PINECONE_API_KEY"] = "pinecone-secret-value"
    environment["PINECONE_INDEX_NAME"] = "legal-current"

    result = get_provider_readiness(environment)

    assert result.status == "ready"
    vector_store = next(provider for provider in result.providers if provider.name == "Vector store")
    assert vector_store.configured is True
    assert vector_store.configured_env_vars == ("PINECONE_API_KEY", "PINECONE_INDEX_NAME")
