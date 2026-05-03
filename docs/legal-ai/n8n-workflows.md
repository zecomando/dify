# n8n workflows — Legal AI Chat

## Princípio

O n8n não deve estar no caminho crítico da resposta do chat. Deve executar tarefas assíncronas de ingestão, monitorização, reprocessamento e notificação.

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
    aguardar conclusão
    validar chunks
    arquivar versão anterior
    promover nova versão
    notificar admin
```

### Critério de sucesso

Alterações legislativas relevantes são detetadas e ficam em `pending_review` ou `chat_ready`.

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
POST /ingestion/source
  ↓
Validar documento
  ↓
Se válido: pending_review ou chat_ready
  ↓
Notificar utilizador/admin
```

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
Monitorizar progresso
  ↓
Comparar métricas de retrieval
  ↓
Notificar resultado
```

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

## Workflow 7 — Cost monitor

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

## Boas práticas

- Usar credenciais separadas por ambiente.
- Não guardar segredos em workflows exportados.
- Usar retries com backoff.
- Evitar crawls sem limite explícito.
- Guardar logs de execução.
- Enviar falhas críticas para canal de alerta.
