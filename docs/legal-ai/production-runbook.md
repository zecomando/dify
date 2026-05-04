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
- Verificar custos.
- Verificar alertas.
- Verificar falhas de validação.

### Semanal

- Executar evaluation suite.
- Rever feedback negativo.
- Rever documentos em `pending_review`.
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

## Modo degradado seguro

Quando algum componente crítico falha, o sistema deve preferir abstenção a resposta sem fonte.

Mensagem padrão:

> O serviço não consegue validar a resposta com segurança neste momento. Por isso, não devo fornecer uma conclusão jurídica.
