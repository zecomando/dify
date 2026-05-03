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

Set `LEGAL_ENGINE_ADMIN_TOKEN` to protect all `/admin/*` endpoints with `X-Admin-Token`.

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
  -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{}"
```

The API response includes the persisted evaluation run ID. Retrieve it with:

```bash
curl -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  http://127.0.0.1:8000/admin/evaluation/runs/<run_id>
```

## Docker

Build and start locally from this directory:

```bash
export LEGAL_ENGINE_ADMIN_TOKEN="change-me"
docker compose up --build
```

The compose file mounts `../docs/legal-ai` read-only, stores SQLite data in the `legal-engine-data` volume, and requires `LEGAL_ENGINE_ADMIN_TOKEN`.

## Initial ingestion smoke

```bash
curl -X POST http://127.0.0.1:8000/ingestion/source \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://dre.pt/dre/legislacao-consolidada/codigo-civil","raw_text":"Artigo 1.º\nA responsabilidade civil depende dos pressupostos legais.","promote_if_valid":true}'

curl -X POST http://127.0.0.1:8000/chat/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"responsabilidade civil"}'

curl -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  http://127.0.0.1:8000/admin/documents
```
