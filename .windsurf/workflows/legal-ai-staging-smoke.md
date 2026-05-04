---
description: Run the Legal AI local/staging smoke validation
---
# Legal AI staging smoke

Use this workflow to validate that `legal-engine-api` is ready for local demo or staging/Dify smoke.

## Preconditions

1. Work from the repository root: `c:\wamp64\www\dify\dify`.
2. Ensure `LEGAL_ENGINE_ADMIN_TOKEN` is set outside the repository for API admin checks.
3. Ensure `LEGAL_ENGINE_BASE_URL` points to the running API, for example `http://127.0.0.1:8000`.
4. For persistent local/staging smoke, ensure `LEGAL_ENGINE_DATABASE_PATH` points to the SQLite database used by the running API.
5. Do not commit secrets, generated databases, or exported workflows containing credentials.

## CLI quality gates

Run these from the repository root.

// turbo
1. Run backend tests:

```powershell
uv run --project legal-engine-api pytest
```

// turbo
2. Run Ruff lint:

```powershell
uv run --project legal-engine-api ruff check app tests
```

// turbo
3. Run Ruff format check:

```powershell
uv run --project legal-engine-api ruff format --check app tests
```

// turbo
4. Run deterministic evaluation:

```powershell
uv run --project legal-engine-api legal-eval
```

// turbo
5. Run deterministic seed-to-chat demo:

```powershell
uv run --project legal-engine-api legal-demo
```

## API smoke

Only run these after `legal-engine-api` is already running and reachable at `LEGAL_ENGINE_BASE_URL`.

6. Confirm health:

```powershell
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/health" -Method Get
```

7. Seed the initial corpus through the admin API:

```powershell
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/corpus/seed" -Method Post -Headers @{ "X-Admin-Token" = $env:LEGAL_ENGINE_ADMIN_TOKEN }
```

8. Ask an answerable canonical question:

```powershell
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/chat/answer" -Method Post -ContentType "application/json" -Body '{"question":"Quais são os pressupostos da responsabilidade civil extracontratual?"}'
```

9. Confirm documents are visible to admin:

```powershell
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/documents" -Method Get -Headers @{ "X-Admin-Token" = $env:LEGAL_ENGINE_ADMIN_TOKEN }
```

10. Confirm ingestion jobs are visible to admin:

```powershell
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/ingestion/jobs" -Method Get -Headers @{ "X-Admin-Token" = $env:LEGAL_ENGINE_ADMIN_TOKEN }
```

11. Run the persisted evaluation through the admin API:

```powershell
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/evaluation/run" -Method Post -ContentType "application/json" -Headers @{ "X-Admin-Token" = $env:LEGAL_ENGINE_ADMIN_TOKEN } -Body '{}'
```

## Dify smoke

12. Import `docs/legal-ai/dify-chat-answer.yml` into Dify.
13. Configure the HTTP node to call `POST $env:LEGAL_ENGINE_BASE_URL/chat/answer` or the equivalent URL reachable from the Dify runtime.
14. Ask the three canonical smoke questions:

```text
Quais são os pressupostos da responsabilidade civil extracontratual?
```

```text
No RGPD da União Europeia, quais são as bases de licitude para tratamento de dados pessoais?
```

```text
Qual é a orientação dominante sobre uma questão jurídica local sem corpus indexado?
```

15. Record the following evidence for the smoke report:

- `audit_id` for each Dify/API answer.
- `evaluation_run_id` from `/admin/evaluation/run`.
- Number of `chat_ready` documents.
- Number of ingestion jobs and any `rejected` jobs.

## Pass criteria

- Tests, lint, format check, `legal-eval`, and `legal-demo` pass.
- Health endpoint responds successfully.
- Corpus seed reports zero unexpected rejected jobs.
- API answerable question returns `pass` with evidence and `audit_id`.
- API/Dify no-source question abstains.
- Admin documents, jobs, audits, and evaluation run are queryable with `X-Admin-Token`.
