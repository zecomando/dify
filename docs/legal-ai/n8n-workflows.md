# n8n workflows — Legal AI Chat

## Princípio

O n8n não deve estar no caminho crítico da resposta do chat. Deve executar tarefas assíncronas de ingestão, monitorização, reprocessamento e notificação.

## Estado atual dos endpoints

O `legal-engine-api` já expõe endpoints suficientes para os primeiros workflows operacionais:

- `POST /ingestion/source` para ingestão manual com texto/metadados.
- `POST /ingestion/crawl-url` para fetch/parsing inicial de DRE/EUR-Lex ou triagem segura de outras URLs.
- `POST /admin/reindex` para reprocessamento.
- `GET /admin/ingestion/jobs` e `GET /admin/ingestion/jobs/{job_id}` para monitorização de jobs.
- `POST /admin/corpus/seed` para preparar demo/staging local.
- `POST /admin/evaluation/run` e `GET /admin/evaluation/runs` para quality gates.

Os workflows devem usar `X-Admin-Token` nos endpoints admin e nunca guardar o token no JSON exportado do workflow.

## Ordem de implementação recomendada

1. **Manual URL ingestion**: já pode ser prototipado com endpoints existentes.
2. **Reindex schedule**: já pode usar `/admin/reindex` e `/admin/ingestion/jobs`.
3. **Evaluation run**: já pode usar `/admin/evaluation/run`.
4. **Cost monitor**: pode ler auditorias, mas custos reais dependem de providers externos.
5. **DRE/EUR-Lex watchers**: já podem começar com listas pequenas e revisão; hardening de parsing/versionamento vem depois.

## Convenções comuns

- Usar credenciais por ambiente, nunca hardcoded.
- Configurar `LEGAL_ENGINE_BASE_URL` e `LEGAL_ENGINE_ADMIN_TOKEN` no ambiente do n8n.
- Definir timeout em todos os HTTP nodes.
- Usar retries com backoff exponencial.
- Guardar `job_id`, `document_id`, `audit_id` e `evaluation_run_id` nos logs do workflow.
- Enviar falhas críticas para canal de alerta.
- Limitar crawls e listas de URLs por execução.
- Tratar `rejected` como resultado operacional explícito, não como erro silencioso.

## Exports importáveis

Os workflows exportáveis ficam em `docs/legal-ai/n8n/`:

- `local-staging-seed-smoke.json`: smoke manual/pós-deploy com seed, listagem de documentos e pergunta canónica.
- `manual-url-ingestion.json`: webhook interno para validar URL, executar `/ingestion/crawl-url` e consultar job.
- `reindex-schedule.json`: schedule semanal para `/admin/reindex`, com filtros opcionais por ambiente.
- `evaluation-run.json`: schedule diário para `/admin/evaluation/run` e validação de `passed=true`.
- `ingestion-job-alerts.json`: schedule horário para consultar jobs `rejected` e falhar explicitamente quando existirem rejeições.

Antes de importar:

- Definir `LEGAL_ENGINE_BASE_URL`, por exemplo `http://legal-engine-api:8000`.
- Definir `LEGAL_ENGINE_ADMIN_TOKEN` como segredo de ambiente do n8n.
- Opcionalmente definir `LEGAL_ENGINE_REINDEX_SOURCE`, `LEGAL_ENGINE_REINDEX_JURISDICTION`, `LEGAL_ENGINE_REINDEX_DOCUMENT_IDS` e `LEGAL_ENGINE_EVALS_DIR`.
- Opcionalmente definir `LEGAL_ENGINE_INGESTION_ALERT_LIMIT` entre 1 e 100 para limitar a amostra de jobs rejeitados.
- Confirmar que o `legal-engine-api` está acessível a partir do runtime do n8n.

Critério de importação:

- O JSON deve importar sem credenciais embutidas.
- Os HTTP nodes devem usar expressões `$env` para URL/token.
- Os `Code` nodes devem falhar explicitamente quando `status=rejected`, `passed=false`, falta `audit_id` ou não há evidência oficial.

## Workflow 0 — Local/staging seed smoke

### Trigger — Local/staging seed smoke

Manual ou pós-deploy em staging.

### Fluxo — Local/staging seed smoke

```text
Manual trigger
  ↓
POST /admin/corpus/seed
  ↓
GET /admin/documents
  ↓
POST /chat/answer com pergunta canónica
  ↓
Verificar verdict, evidence e audit_id
  ↓
Notificar resultado
```

### Critério de sucesso

O corpus inicial fica `chat_ready`, a pergunta canónica retorna `pass` com fontes oficiais e existe `audit_id`.

## Workflow 1 — Daily DRE watch

### Frequência — Daily DRE watch

Todos os dias às 09:15 Europe/Lisbon.

### Fluxo — Daily DRE watch

```text
Cron
  ↓
Carregar seed de diplomas monitorizados
  ↓
Consultar/fetch URLs oficiais
  ↓
Calcular hash
  ↓
Comparar com último hash guardado
  ↓
Se mudou:
    POST /ingestion/source
    GET /admin/ingestion/jobs/{job_id}
    validar chunks
    arquivar versão anterior
    promover nova versão
    notificar admin
```

### Critério de sucesso

Alterações legislativas relevantes são detetadas e ficam em `pending_review` ou `chat_ready`.

### Dependências técnicas

- Fetch remoto DRE inicial implementado.
- Parser DRE inicial preserva texto/artigos; parser estrutural robusto ainda é necessário.
- Versionamento/arquivamento de documentos.
- Reindexação vetorial quando o modelo local/externo de embeddings ou o chunker mudar.

## Workflow 2 — EUR-Lex refresh

### Frequência — EUR-Lex refresh

Diário para atos críticos; semanal para restante corpus.

### Fluxo — EUR-Lex refresh

```text
Cron
  ↓
Carregar lista CELEX/ELI
  ↓
Verificar versão consolidada atual
  ↓
Comparar data de versão/hash
  ↓
Ingerir alterações
  ↓
Atualizar índice
  ↓
Guardar cadeia de atos modificativos
```

### Dependências técnicas

- Fetch EUR-Lex inicial por URL implementado.
- Parser inicial preserva CELEX e texto/artigos.
- Parser de ELI, anexos e versões consolidadas ainda é necessário.

## Workflow 3 — DGSI weekly watch

### Frequência — DGSI weekly watch

Semanal.

### Fluxo — DGSI weekly watch

```text
Cron
  ↓
Executar queries por área jurídica
  ↓
Recolher resultados
  ↓
Extrair metadados
  ↓
Filtrar tribunais e temas prioritários
  ↓
Criar ingestão em pending_review
  ↓
Notificar revisor humano
```

### Critério de sucesso

Decisões novas entram em `pending_review`, nunca diretamente em `chat_ready`, salvo política editorial explícita.

### Dependências técnicas

- Extração de tribunal, data, processo, sumário e URL oficial.
- Fila de revisão humana.
- Critérios editoriais por área jurídica.

## Workflow 4 — Manual URL ingestion

### Trigger — Manual URL ingestion

Webhook interno.

### Fluxo — Manual URL ingestion

```text
Webhook recebe URL
  ↓
Validar domínio contra source-policy
  ↓
POST /ingestion/crawl-url
  ↓
Se autoridade suportada:
    documento/job é criado automaticamente
Se autoridade ainda não suportada:
    preparar bruto/metadados e usar POST /ingestion/source
  ↓
GET /admin/ingestion/jobs/{job_id}
  ↓
Validar status, document_id e error_message
  ↓
Notificar utilizador/admin
```

### Payload mínimo — Manual URL ingestion

```json
{
  "source_url": "https://dre.pt/dre/legislacao-consolidada/exemplo",
  "raw_text": "Artigo 1.º\nTexto extraído ou colado pelo operador.",
  "source": "DRE",
  "jurisdiction": "portugal",
  "document_type": "legislation",
  "area": ["civil"],
  "legal_metadata": {
    "article_number": "1"
  },
  "promote_if_valid": false
}
```

### Critério de sucesso

O operador recebe `job_id`, status final, motivo de rejeição quando existir e link para revisão do documento.

## Workflow 5 — Reindex schedule

### Frequência — Reindex schedule

Semanal ou quando há mudança de embeddings/chunker.

### Fluxo — Reindex schedule

```text
Cron
  ↓
Selecionar documentos afetados
  ↓
POST /admin/reindex
  ↓
GET /admin/ingestion/jobs/{job_id}
  ↓
Comparar métricas de retrieval
  ↓
Notificar resultado
```

### Critério de sucesso

Documentos afetados são reprocessados, failures ficam visíveis nos jobs e uma amostra canónica de retrieval/evidence continua a passar.

## Workflow 6 — Evaluation run

### Frequência — Evaluation run

Diário durante desenvolvimento; semanal em produção.

### Fluxo — Evaluation run

```text
Cron
  ↓
Carregar dataset de avaliação
  ↓
Executar perguntas
  ↓
Guardar answer_audits
  ↓
Calcular métricas
  ↓
Se quality gate falha:
    alertar equipa
    bloquear deploy se crítico
```

### Implementação atual

O workflow pode chamar `POST /admin/evaluation/run` com `{}` para usar o dataset default versionado em `docs/legal-ai/evals`.

### Critério de sucesso

O run fica persistido, `passed=true` é exigido para deploy, e falhas geram alerta com lista dos casos regressivos.

## Workflow 7 — Ingestion job alerts

### Frequência — Ingestion job alerts

Horário em staging/beta, ajustável pelo operador.

### Fluxo — Ingestion job alerts

```text
Cron
  ↓
Preparar limite operacional
  ↓
GET /admin/ingestion/jobs?status=rejected
  ↓
Se existirem jobs rejeitados:
    lançar erro explícito com total e amostra
Se não existirem:
    devolver status passed
```

### Implementação atual

O workflow exportável `ingestion-job-alerts.json` usa apenas `LEGAL_ENGINE_BASE_URL`, `LEGAL_ENGINE_ADMIN_TOKEN` e opcionalmente `LEGAL_ENGINE_INGESTION_ALERT_LIMIT`. Não contém credenciais embutidas e é validado por `legal-n8n-validate`.

### Critério de sucesso

Rejeições de ingestão ficam visíveis como falha operacional no n8n, com `job_id`, `source` e `error_message` suficientes para triagem pelo operador.

## Workflow 8 — Cost monitor

### Frequência — Cost monitor

Diário.

### Fluxo — Cost monitor

```text
Cron
  ↓
Ler custos estimados do audit log
  ↓
Agrupar por modelo/provider
  ↓
Comparar com orçamento
  ↓
Alertar se exceder limite
```

### Estado

No MVP local, custos são estimados e determinísticos. O workflow torna-se operacionalmente relevante quando providers LLM, embeddings, rerank e crawler estiverem ativos.

## Boas práticas

- Usar credenciais separadas por ambiente.
- Não guardar segredos em workflows exportados.
- Usar retries com backoff.
- Evitar crawls sem limite explícito.
- Guardar logs de execução.
- Enviar falhas críticas para canal de alerta.
