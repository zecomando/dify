# Legal Engine API

FastAPI service for the Legal AI Chat evidence engine. The service is deterministic, source-grounded, and does not call LLMs or external APIs.

## Scope

- Load the versioned source policy from `docs/legal-ai/source-policy.yml`.
- Ingest official legal text into SQLite from manual text or initial remote crawl support for DRE/EUR-Lex.
- Chunk legal text deterministically.
- Persist legal metadata and enforce required source-policy metadata/identifiers before `chat_ready`.
- Retrieve and rerank persisted `chat_ready` chunks.
- Build evidence only from authoritative official sources.
- Generate cited deterministic answers.
- Validate answers with anti-hallucination guardrails for URLs, articles, processes, ECLI, and CELEX.
- Persist answer audits and evaluation runs.

## Local commands

```bash
uv sync --project legal-engine-api --group dev
uv run --project legal-engine-api pytest
uv run --project legal-engine-api ruff check app tests
uv run --project legal-engine-api ruff format --check app tests
uv run --project legal-engine-api legal-seed
uv run --project legal-engine-api legal-demo
uv run --project legal-engine-api legal-smoke --json
uv run --project legal-engine-api legal-n8n-validate
uv run --project legal-engine-api legal-readiness --skip-eval
uv run --project legal-engine-api uvicorn app.main:app --reload
```

## Configuration

Set `LEGAL_ENGINE_DATABASE_PATH` to override the default SQLite path.

Set `LEGAL_ENGINE_DATABASE_URL` to use PostgreSQL instead of SQLite. SQLite remains the default for local development.

Set `LEGAL_SOURCE_POLICY_PATH` to override the default policy path.

Set `LEGAL_ENGINE_ADMIN_TOKEN` to protect all `/admin/*` endpoints with `X-Admin-Token`.

Use `.env.example` as the non-secret template for local/staging environment variables.

## Database operations

Initialize or update the configured database schema:

```bash
uv run --project legal-engine-api legal-db-migrate
uv run --project legal-engine-api legal-db-migrate --database-url "$LEGAL_ENGINE_DATABASE_URL"
```

Create and restore backups:

```bash
uv run --project legal-engine-api legal-db-backup --output .data/legal_engine.backup.sqlite3
uv run --project legal-engine-api legal-db-restore --input .data/legal_engine.backup.sqlite3 --overwrite
```

When `LEGAL_ENGINE_DATABASE_URL` or `--database-url` is set, backup and restore use `pg_dump` and `pg_restore`.

## Local/staging readiness

Run the readiness gates without paid providers:

```bash
uv run --project legal-engine-api legal-readiness
uv run --project legal-engine-api legal-readiness --require-admin-token --database-url "$LEGAL_ENGINE_DATABASE_URL"
uv run --project legal-engine-api legal-readiness --require-admin-token --require-postgresql --database-url "$LEGAL_ENGINE_DATABASE_URL"
```

The command checks schema initialization, source policy loading, optional admin token presence, seed, deterministic demo, and evaluation gates. Use `--require-postgresql` for staging gates that must fail unless `LEGAL_ENGINE_DATABASE_URL` or `--database-url` selects PostgreSQL.

Run a traceable local/staging smoke report when you need canonical `audit_id` values, a persisted `evaluation_run_id`, seed counts, and diagnostics in one output:

```bash
uv run --project legal-engine-api legal-smoke --json
uv run --project legal-engine-api legal-smoke --database-url "$LEGAL_ENGINE_DATABASE_URL" --json
```

The smoke command seeds the corpus, runs the canonical chat cases, persists an evaluation run, and reports document/job/audit/evaluation counts without requiring paid providers.

The readiness command also validates the exported n8n workflows under `docs/legal-ai/n8n`. You can run that gate independently:

```bash
uv run --project legal-engine-api legal-n8n-validate
```

## Local MVP status

The local MVP path is deterministic and runs without external LLM, embedding, rerank, or vector database providers. Local hash embeddings are persisted in SQLite with stable vector IDs and combined with lexical retrieval through replaceable embedding/vector store/rerank interfaces. Documents are only promoted to `chat_ready` when they have persisted chunks and satisfy the configured source-policy requirements for document type, required metadata, and required legal identifiers. Manual and admin promotion use the same safe promotion rules.

Validated locally with:

```bash
uv run pytest
uv run ruff check app tests
uv run legal-demo
```

## API smoke checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/openapi.json
```

## Remote crawl MVP

`POST /ingestion/crawl-url` validates the URL against `source-policy.yml`. For supported official DRE, EUR-Lex, DGSI, Tribunal Constitucional, Curia/InfoCuria, and HUDOC URLs, it fetches remote HTML/text, normalizes it into raw text, extracts basic legal metadata such as ELI, CELEX, court, decision date, process/case/application numbers, persists raw text/chunks/jobs, and promotes to `chat_ready` only when source-policy requirements pass.
Remote fetch rejects unsupported non-text content types and responses larger than the configured byte limit instead of silently ingesting truncated or binary content.

Tests use an injected fake fetcher and do not call live official websites.

## Main endpoints

- `GET /health`
- `POST /source-policy/check-url`
- `POST /ingestion/source`
- `POST /ingestion/crawl-url`
- `POST /retrieval/search`
- `POST /chat/answer`
- `GET /admin/documents`
- `GET /admin/documents/review-queue`
- `GET /admin/documents/{document_id}`
- `GET /admin/documents/{document_id}/chunks`
- `POST /admin/documents/{document_id}/status`
- `GET /admin/audits`
- `GET /admin/audit/{answer_id}`
- `GET /admin/feedback/triage`
- `POST /admin/corpus/seed`
- `GET /admin/ingestion/jobs`
- `GET /admin/ingestion/jobs/{job_id}`
- `POST /admin/evaluation/run`
- `GET /admin/evaluation/runs`
- `GET /admin/evaluation/runs/{run_id}`

`GET /admin/documents/review-queue` lists `pending_review` documents with `promotion_blockers` and `can_promote_to_chat_ready`. `POST /admin/documents/{document_id}/status` is the local operational review gate. It requires a non-empty `change_note`, returns `409` with explicit blockers when `chat_ready` is blocked by missing chunks or source-policy requirements, and persists the review note when approving, rejecting, or archiving a document.

The same review queue can be inspected locally without starting FastAPI:

```bash
uv run --project legal-engine-api legal-review-queue
uv run --project legal-engine-api legal-review-queue --json
```

Use `--source`, `--jurisdiction`, `--document-type`, `--limit`, and `--offset` to narrow the operational queue.

Ingestion jobs can also be inspected locally with errors and linked documents:

```bash
uv run --project legal-engine-api legal-ingestion-jobs
uv run --project legal-engine-api legal-ingestion-jobs --status rejected --json
```

Use `--status`, `--mode`, `--source`, `--limit`, and `--offset` to investigate failed or pending ingestion work.
Reindex jobs may finish as `completed` while still carrying an `error_message` when some requested documents were skipped because no raw text was persisted for them.

Negative answer feedback can be triaged with answer audit context:

```bash
uv run --project legal-engine-api legal-feedback-triage
uv run --project legal-engine-api legal-feedback-triage --category legal_error --json
```

Use `--category`, `--session-id`, `--user-id`, `--limit`, and `--offset` to prepare a focused legal review export without direct database access.

## Initial deterministic corpus

Seed the local SQLite database with the deterministic demo corpus:

```bash
uv run --project legal-engine-api legal-seed
uv run --project legal-engine-api legal-seed --json
```

Or through the protected admin API:

```bash
curl -X POST http://127.0.0.1:8000/admin/corpus/seed \
  -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN"
```

The seed operation is idempotent by `source_url`. The initial corpus covers DRE legislation, EUR-Lex legislation/treaty material, selected official case-law metadata, TED, and BASE examples. All seeded documents must satisfy `source-policy.yml` before becoming `chat_ready`.

## Local demo smoke

Run the deterministic seed-to-chat smoke without starting FastAPI or Dify:

```bash
uv run --project legal-engine-api legal-demo
uv run --project legal-engine-api legal-demo --json
```

The command seeds the initial corpus, runs representative answerable and no-source questions through the real chat pipeline, prints verdicts, evidence counts, sources, and audit IDs, and exits with a non-zero status if an expected demo case fails.

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
curl -X POST http://127.0.0.1:8000/admin/corpus/seed \
  -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN"

curl -X POST http://127.0.0.1:8000/chat/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"Quais são os pressupostos da responsabilidade civil extracontratual?"}'

curl -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  http://127.0.0.1:8000/admin/documents
```
