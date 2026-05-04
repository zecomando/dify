from app.provider_readiness import get_provider_readiness


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
