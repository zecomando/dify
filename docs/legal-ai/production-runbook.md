# Production runbook — Legal AI Chat

## Objetivo

Definir procedimentos operacionais para manter o serviço disponível, seguro, auditável e juridicamente controlado.

## Ambientes

- `local`
- `staging`
- `production`

## Serviços críticos

- Dify.
- `legal-engine-api`.
- PostgreSQL.
- Redis.
- Pinecone/Qdrant Cloud.
- Object storage.
- Langfuse.
- n8n.
- Providers LLM/embeddings/rerank/crawl.

## Deploy

### Pré-deploy

- Executar testes unitários.
- Executar evaluation suite mínima.
- Confirmar migrations com `legal-db-migrate`.
- Confirmar source policy.
- Confirmar `.env` de ambiente.
- Confirmar `LEGAL_ENGINE_ADMIN_TOKEN` definido e guardado como secret do ambiente.
- Confirmar backups recentes com `legal-db-backup` ou snapshot gerido.

### Execução de deploy

- Fazer deploy em staging.
- Executar smoke tests.
- Executar 10 perguntas canónicas.
- Verificar Langfuse traces.
- Promover para produção.

### Pós-deploy

- Monitorizar logs por 30 minutos.
- Verificar latência.
- Verificar custos.
- Verificar abstenções anómalas.
- Verificar falhas de provider.

## Smoke tests

- Health check.
- Pergunta simples sobre artigo conhecido.
- Pergunta que deve abster.
- Pergunta com identificador falso.
- Pergunta com fonte consolidada.
- Consulta de audit record com `X-Admin-Token`.

## Staging mínimo

1. Definir `LEGAL_ENGINE_ADMIN_TOKEN` fora do repositório.
2. Subir `legal-engine-api` com volume persistente para SQLite ou `LEGAL_ENGINE_DATABASE_URL` para PostgreSQL.
3. Confirmar `GET /health`.
4. Semear o corpus inicial com `legal-seed` ou `POST /admin/corpus/seed`.
5. Confirmar `/admin/documents` com `X-Admin-Token`.
6. Executar `legal-demo` antes de abrir o Dify.
7. Importar `docs/legal-ai/dify-chat-answer.yml` no Dify.
8. Executar os smoke tests do chat no Dify.
9. Em staging PostgreSQL, executar `legal-readiness --require-admin-token --require-postgresql --database-url $env:LEGAL_ENGINE_DATABASE_URL`.

## PostgreSQL local-first

Antes de usar cloud ou servidores externos, validar o caminho PostgreSQL com uma instância local.

### Preparação PowerShell

```powershell
$env:PATH = "C:\Program Files\PostgreSQL\16\bin;$env:PATH"
$env:PGPASSWORD = Read-Host "PostgreSQL password"
$env:LEGAL_ENGINE_DATABASE_URL = "postgresql://postgres@127.0.0.1:5432/legal_engine_staging"
$env:LEGAL_ENGINE_ADMIN_TOKEN = Read-Host "Legal Engine admin token"
$env:LEGAL_ENGINE_BASE_URL = "http://127.0.0.1:8000"
```

Criar a base local se ainda não existir:

```powershell
$exists = & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres -w -P pager=off -tAc "SELECT 1 FROM pg_database WHERE datname = 'legal_engine_staging';"
if ($exists -ne "1") {
  & "C:\Program Files\PostgreSQL\16\bin\createdb.exe" -h 127.0.0.1 -p 5432 -U postgres -w legal_engine_staging
}
```

### Gates PostgreSQL locais

```powershell
uv run --project legal-engine-api legal-db-migrate --database-url $env:LEGAL_ENGINE_DATABASE_URL
uv run --project legal-engine-api legal-seed --database-url $env:LEGAL_ENGINE_DATABASE_URL --json
uv run --project legal-engine-api legal-demo --database-url $env:LEGAL_ENGINE_DATABASE_URL
uv run --project legal-engine-api legal-eval --database-url $env:LEGAL_ENGINE_DATABASE_URL
uv run --project legal-engine-api legal-readiness --database-url $env:LEGAL_ENGINE_DATABASE_URL --require-admin-token --require-postgresql
```

### Backup e restore locais

```powershell
uv run --project legal-engine-api legal-db-backup `
  --database-url $env:LEGAL_ENGINE_DATABASE_URL `
  --output legal-engine-api/.data/legal_engine_staging_pg.dump

& "C:\Program Files\PostgreSQL\16\bin\dropdb.exe" -h 127.0.0.1 -p 5432 -U postgres -w --if-exists legal_engine_restore_check
& "C:\Program Files\PostgreSQL\16\bin\createdb.exe" -h 127.0.0.1 -p 5432 -U postgres -w legal_engine_restore_check

uv run --project legal-engine-api legal-db-restore `
  --database-url "postgresql://postgres@127.0.0.1:5432/legal_engine_restore_check" `
  --input legal-engine-api/.data/legal_engine_staging_pg.dump

& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d legal_engine_restore_check -w -P pager=off -c "SELECT COUNT(*) AS documents FROM legal_documents; SELECT COUNT(*) AS jobs FROM source_ingestion_jobs;"
```

### API local contra PostgreSQL

```powershell
uv run --project legal-engine-api uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Executar smoke HTTP noutra sessão PowerShell com as mesmas variáveis:

```powershell
$headers = @{ "X-Admin-Token" = $env:LEGAL_ENGINE_ADMIN_TOKEN }

Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/health" -Method Get
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/corpus/seed" -Method Post -Headers $headers

$answerJson = @{ question = "Quais sao os pressupostos da responsabilidade civil extracontratual?" } | ConvertTo-Json -Compress
$answerBytes = [System.Text.Encoding]::UTF8.GetBytes($answerJson)
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/chat/answer" -Method Post -ContentType "application/json; charset=utf-8" -Body $answerBytes

Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/documents" -Method Get -Headers $headers
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/ingestion/jobs" -Method Get -Headers $headers

$evalBytes = [System.Text.Encoding]::UTF8.GetBytes("{}")
Invoke-RestMethod -Uri "$env:LEGAL_ENGINE_BASE_URL/admin/evaluation/run" -Method Post -ContentType "application/json; charset=utf-8" -Headers $headers -Body $evalBytes
```

### Critérios de aprovação PostgreSQL local

- `legal-db-migrate`, `legal-seed`, `legal-demo`, `legal-eval` e `legal-readiness` passam com `LEGAL_ENGINE_DATABASE_URL`.
- O seed termina com documentos `chat_ready` e zero rejeições inesperadas.
- `legal-demo` responde às perguntas canónicas e abstém quando não há corpus suficiente.
- Backup com `pg_dump` e restore com `pg_restore` são testados numa base limpa.
- O smoke HTTP local retorna health `ok`, documentos, jobs, `audit_id` e evaluation run persistido.
- A password PostgreSQL e o admin token não ficam no repositório nem embutidos na URL.

## Staging smoke reproduzível

### Objetivo

Validar que um ambiente `local` ou `staging` consegue responder com fonte oficial, abster quando não há corpus suficiente, guardar auditoria e executar quality gates sem depender de estado manual oculto.

### Variáveis obrigatórias

- `LEGAL_ENGINE_ADMIN_TOKEN`: token secreto usado em todos os endpoints `/admin/*`.
- `LEGAL_ENGINE_DATABASE_PATH`: caminho persistente para SQLite no MVP local/staging.
- `LEGAL_ENGINE_DATABASE_URL`: URL PostgreSQL para staging/produção quando não se usa SQLite.
- `LEGAL_SOURCE_POLICY_PATH`: opcional; usar apenas quando a source policy não estiver no caminho default.
- `LEGAL_ENGINE_BASE_URL`: URL acessível pelo Dify e pelos comandos de smoke, por exemplo `http://127.0.0.1:8000`.

### Ordem obrigatória

1. Executar quality gates locais do pacote.
2. Subir `legal-engine-api`.
3. Confirmar health check.
4. Semear corpus inicial.
5. Executar `legal-demo` contra a mesma base persistente.
6. Executar evaluation por API.
7. Confirmar documentos `chat_ready`.
8. Confirmar jobs de ingestão sem rejeições inesperadas.
9. Importar `docs/legal-ai/dify-chat-answer.yml` no Dify.
10. Configurar o HTTP node para `POST $LEGAL_ENGINE_BASE_URL/chat/answer`.
11. Executar três perguntas Dify: respondível, europeia respondível e sem corpus suficiente.
12. Registar `audit_id`, `evaluation_run_id`, total de documentos e total de jobs.

### Comandos de smoke local/staging

```bash
uv run --project legal-engine-api pytest
uv run --project legal-engine-api ruff check app tests
uv run --project legal-engine-api ruff format --check app tests
uv run --project legal-engine-api legal-eval
uv run --project legal-engine-api legal-db-migrate

uv run --project legal-engine-api legal-seed --json

uv run --project legal-engine-api legal-demo

curl "$LEGAL_ENGINE_BASE_URL/health"

curl -X POST "$LEGAL_ENGINE_BASE_URL/admin/corpus/seed" \
  -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN"

curl -X POST "$LEGAL_ENGINE_BASE_URL/chat/answer" \
  -H "Content-Type: application/json" \
  -d '{"question":"Quais são os pressupostos da responsabilidade civil extracontratual?"}'

curl -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  "$LEGAL_ENGINE_BASE_URL/admin/documents"

curl -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  "$LEGAL_ENGINE_BASE_URL/admin/ingestion/jobs"

curl -X POST "$LEGAL_ENGINE_BASE_URL/admin/evaluation/run" \
  -H "X-Admin-Token: $LEGAL_ENGINE_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{}"
```

### Perguntas canónicas para Dify

Pergunta respondível:

```text
Quais são os pressupostos da responsabilidade civil extracontratual?
```

Pergunta europeia respondível:

```text
No RGPD da União Europeia, quais são as bases de licitude para tratamento de dados pessoais?
```

Pergunta que deve abster:

```text
Qual é a orientação dominante sobre uma questão jurídica local sem corpus indexado?
```

### Critérios de aprovação

- `GET /health` retorna sucesso.
- `legal-demo` termina com `PASS`.
- `legal-eval` termina com `passed=True`.
- `POST /admin/evaluation/run` retorna um run com `passed=true`.
- `/admin/documents` mostra documentos `chat_ready`.
- `/admin/ingestion/jobs` não mostra rejeições inesperadas no seed.
- Cada resposta Dify mostra resposta final ou abstenção, nunca draft inválido.
- Cada resposta Dify expõe ou permite rastrear `audit_id`.
- A pergunta sem corpus suficiente abstém.

## Backups

### PostgreSQL

- Definir `LEGAL_ENGINE_DATABASE_URL` como secret do ambiente.
- Executar `legal-db-migrate` antes de semear ou abrir tráfego.
- Criar backup manual com `legal-db-backup --output /backups/legal-engine.dump` antes de deploys de risco.
- Restaurar com `legal-db-restore --input /backups/legal-engine.dump`.
- Backup diário via `pg_dump` ou snapshots geridos.
- Retenção mínima de 30 dias.
- Teste de restore mensal.

### SQLite local/staging

- Usar `LEGAL_ENGINE_DATABASE_PATH` em volume persistente.
- Criar backup com `legal-db-backup --output /backups/legal-engine.sqlite3`.
- Restaurar com `legal-db-restore --input /backups/legal-engine.sqlite3 --overwrite`.

### Object storage

- Versioning ativo.
- Lifecycle policy documentada.
- Retenção de raw documents.

### Configurações

- Export de workflows Dify.
- Export de workflows n8n.
- Source policy versionada.
- Prompts versionados.

## Incidentes

### Incidente: validador indisponível

Ação:

- Ativar modo degradado seguro.
- Bloquear respostas conclusivas.
- Devolver abstenção temporária.
- Alertar equipa.

### Incidente: vector DB indisponível

Ação:

- Bloquear geração.
- Devolver mensagem de indisponibilidade.
- Não fazer fallback para conhecimento do modelo.

### Incidente: provider LLM indisponível

Ação:

- Usar fallback configurado se cumprir política.
- Se não houver fallback, devolver indisponibilidade.

### Incidente: source policy corrompida ou ausente

Ação:

- Bloquear respostas jurídicas.
- Colocar serviço em manutenção parcial.
- Restaurar versão anterior.

### Incidente: alucinação crítica detetada em produção

Ação:

- Marcar audit record.
- Retirar resposta da UI se aplicável.
- Criar regression test.
- Rever retrieval/evidence/validator.
- Reexecutar evaluation suite.
- Comunicar utilizadores afetados se necessário.

## Manutenção regular

### Diária

- Verificar jobs de ingestão.
- Em operação local sem FastAPI, usar `legal-ingestion-jobs --status rejected --json` para rever erros e documentos associados.
- Rever também jobs `completed` de modo `reindex` com `error_message`, porque indicam reindexação parcial com documentos saltados por falta de texto bruto persistido.
- Verificar custos.
- Verificar alertas.
- Verificar falhas de validação.

### Semanal

- Executar evaluation suite.
- Rever feedback negativo.
- Rever documentos em `pending_review`.
- Usar `/admin/documents/review-queue` para priorizar documentos sem blockers.
- Usar `/admin/feedback/triage` para priorizar feedback negativo com pergunta, resposta final, veredicto e evidência.
- Em operação local sem FastAPI, usar `legal-review-queue`, `legal-feedback-triage` ou os respetivos modos `--json`.
- Aprovar, rejeitar ou arquivar documentos via `/admin/documents/{document_id}/status` com `change_note` auditável.
- Investigar blockers `409` antes de nova tentativa de promoção para `chat_ready`.
- Rever fontes com alterações.

### Mensal

- Testar restore.
- Rever vendors e custos.
- Rever política de retenção.
- Rever source policy.
- Atualizar datasets.

## Rollback

Rollback deve incluir:

- Código.
- Prompts.
- Source policy.
- Configuração de retrieval.
- Modelo/reranker se alterado.
- Base de dados compatível com a versão de código restaurada.

Para rollback local com PostgreSQL:

1. Parar `legal-engine-api`.
2. Restaurar um backup criado antes da alteração de schema para uma base limpa.
3. Confirmar `schema_migrations` antes de arrancar a versão antiga.
4. Executar `legal-db-migrate` com a versão restaurada do código.
5. Executar `legal-demo`, `legal-eval` e smoke HTTP local.

O arranque deve falhar se a base contiver uma migration aplicada que a versão local do código não conhece. Nesse caso, restaurar um backup compatível em vez de arrancar uma versão antiga contra uma base migrada para frente.

## Modo degradado seguro

Quando algum componente crítico falha, o sistema deve preferir abstenção a resposta sem fonte.

Mensagem padrão:

> O serviço não consegue validar a resposta com segurança neste momento. Por isso, não devo fornecer uma conclusão jurídica.
