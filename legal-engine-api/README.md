# Legal Engine API

FastAPI service for the Legal AI Chat evidence engine. The service is deterministic, source-grounded, and does not call LLMs or external APIs.

## Scope

- Load the versioned source policy from `docs/legal-ai/source-policy.yml`.
- Ingest official legal text into SQLite.
- Chunk legal text deterministically.
- Retrieve and rerank persisted `chat_ready` chunks.
- Build evidence only from authoritative official sources.
- Generate cited deterministic answers.
- Validate answers with anti-hallucination guardrails.
- Persist answer audits and evaluation runs.

## Local commands

```bash
uv sync --project legal-engine-api --group dev
uv run --project legal-engine-api pytest
uv run --project legal-engine-api ruff check app tests
uv run --project legal-engine-api ruff format --check app tests
uv run --project legal-engine-api uvicorn app.main:app --reload
```

## Configuration

Set `LEGAL_ENGINE_DATABASE_PATH` to override the default SQLite path.

Set `LEGAL_SOURCE_POLICY_PATH` to override the default policy path.

## API smoke checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/openapi.json
```

## Main endpoints

- `GET /health`
- `POST /source-policy/check-url`
- `POST /ingestion/source`
- `POST /retrieval/search`
- `POST /chat/answer`
- `GET /admin/documents`
- `GET /admin/documents/{document_id}`
- `GET /admin/documents/{document_id}/chunks`
- `POST /admin/documents/{document_id}/status`
- `GET /admin/audits`
- `GET /admin/audit/{answer_id}`
- `POST /admin/evaluation/run`
- `GET /admin/evaluation/runs`
- `GET /admin/evaluation/runs/{run_id}`

## Evaluation quality gates

Run locally:

```bash
uv run --project legal-engine-api legal-eval
uv run --project legal-engine-api legal-eval --json
```

Run through the API:

```bash
curl -X POST http://127.0.0.1:8000/admin/evaluation/run \
  -H "Content-Type: application/json" \
  -d "{}"
```

The API response includes the persisted evaluation run ID. Retrieve it with:

```bash
curl http://127.0.0.1:8000/admin/evaluation/runs/<run_id>
```

## Docker

Build and start locally from this directory:

```bash
docker compose up --build
```

The compose file mounts `../docs/legal-ai` read-only and stores SQLite data in the `legal-engine-data` volume.
