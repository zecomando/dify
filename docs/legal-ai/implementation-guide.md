# Guia de implementação — Legal AI Chat

## Objetivo

Transformar os artefactos deste diretório numa implementação incremental, segura e testável.

## Estado atual validado

O MVP local já existe em `legal-engine-api/` e foi validado com testes automatizados, lint, format check, `legal-eval` e `legal-demo`.

Implementado localmente:

- FastAPI com `/health`, `/chat/answer`, endpoints de classificação, retrieval, evidence, geração, validação e admin.
- Source policy em runtime com validação de domínio, tipo documental, metadados obrigatórios e identificadores jurídicos obrigatórios.
- Persistência SQLite para documentos, texto bruto, chunks, jobs, feedback, auditorias e runs de avaliação.
- Suporte mínimo a PostgreSQL via `LEGAL_ENGINE_DATABASE_URL`, com `legal-db-migrate`, `legal-db-backup` e `legal-db-restore`.
- Ingestão manual/local com SHA-256, chunking por artigo, `legal_metadata` e promoção controlada para `chat_ready`.
- Corpus inicial oficial seedável via `legal-seed` e `POST /admin/corpus/seed`.
- Retrieval lexical/sparse determinístico com filtros jurídicos.
- Evidence builder que só entrega fontes oficiais elegíveis.
- Gerador e validador determinísticos com abstenção segura e bloqueio de identificadores inventados.
- Dify workflow importável para `/chat/answer`.
- Admin API protegida por `X-Admin-Token` para documentos, chunks, auditorias, seed, reindex, evaluations e jobs.

Ainda pendente para beta/produção:

- Hardening de migrations PostgreSQL para produção com estratégia expand/contract.
- Fetch remoto robusto de todas as fontes; DRE/EUR-Lex já têm incremento inicial em `/ingestion/crawl-url`.
- Parser documental robusto para HTML/PDF/XML.
- Providers externos de embeddings/vector store/reranker; índice vetorial local determinístico já existe em SQLite.
- Langfuse tracing.
- n8n workflows exportáveis.
- UI/admin mínima para feedback do utilizador.
- Versionamento temporal completo e comparação entre versões.

## Ordem recomendada

1. Criar `legal-engine-api`. **Feito localmente.**
2. Implementar source policy em código. **Feito localmente.**
3. Criar schema PostgreSQL. **Suporte mínimo feito; hardening de migrations produção pendente.**
4. Implementar ingestão mínima. **Feito localmente para seed/manual; fetch/parsing inicial DRE/EUR-Lex feito via crawl.**
5. Implementar chunking legislativo. **Feito localmente por artigo; chunking estrutural avançado pendente.**
6. Implementar embeddings e vector store. **Feito localmente de forma determinística; providers externos pendentes.**
7. Implementar retrieval híbrido. **Fusão dense/sparse local feita; calibração beta pendente.**
8. Implementar evidence builder. **Feito localmente.**
9. Implementar geração e validação. **Feito localmente de forma determinística; providers LLM pendentes.**
10. Integrar Dify. **Workflow importável feito; validação em ambiente Dify alvo pendente.**
11. Ativar auditoria e Langfuse. **Auditoria local feita; Langfuse pendente.**
12. Executar evaluation suite. **Suite mínima feita; expansão beta pendente.**

## Estrutura inicial recomendada

```text
services/
  legal-engine-api/
    app/
      main.py
      config.py
      dependencies.py
      source_policy/
      ingestion/
      retrieval/
      evidence/
      answering/
      validation/
      audit/
      schemas/
      providers/
    tests/
    pyproject.toml
```

## Interfaces obrigatórias

```text
SourcePolicy
EmbeddingProvider
VectorStore
RerankerProvider
CrawlerProvider
ParserProvider
LLMProvider
AuditStore
```

Estado das interfaces:

- `SourcePolicy`: implementada.
- `AuditStore`: implementado via repositório SQLite local.
- `CrawlerProvider`: incremento inicial implementado com fetch HTTP injetável para `/ingestion/crawl-url`.
- `ParserProvider`: parser inicial DRE/EUR-Lex implementado; parser robusto multi-fonte pendente.
- `EmbeddingProvider`: provider local determinístico implementado; providers externos pendentes.
- `VectorStore`: índice SQLite local por chunk implementado; Pinecone/Qdrant pendente.
- `RerankerProvider`: pendente.
- `LLMProvider`: pendente para providers externos; gerador determinístico local implementado para testes/demo.

## Implementação por milestone

### Milestone 1 — API mínima

Estado: **feito localmente**.

Entregáveis:

- FastAPI com `/health`.
- Configuração por ambiente.
- Autenticação simples por API key interna.
- Logging estruturado.

Critério de aceitação:

- Serviço arranca localmente.
- `/health` responde `ok`.

### Milestone 2 — Source policy

Estado: **feito localmente**.

Entregáveis:

- Loader de `source-policy.yml`.
- Validador de domínio.
- Função `can_ground_answer(url, document_type)`.
- Testes para Classe A, discovery-only e bloqueados.

Critério de aceitação:

- Blog ou escritório nunca pode fundamentar resposta.

### Milestone 3 — Dados e auditoria

Estado: **feito localmente em SQLite; suporte mínimo PostgreSQL implementado para staging/produção**.

Entregáveis:

- Repositórios para documentos, chunks, jobs, auditorias e evaluations.
- Criação de `answer_audits` em todas as respostas.
- Persistência de `legal_metadata`, bruto e SHA-256.
- Migração inicial idempotente via `legal-db-migrate` para SQLite/PostgreSQL.

Critério de aceitação:

- Nenhuma resposta sai sem audit record.
- Cada evidência é rastreável até documento, URL oficial, versão e metadados jurídicos.

### Milestone 4 — Ingestão mínima

Estado: **feito localmente para seed/manual; fetch/parsing inicial DRE/EUR-Lex implementado; parsing robusto multi-fonte pendente**.

Entregáveis:

- Endpoint `/ingestion/source`.
- Endpoint `/ingestion/crawl-url` com fetch HTTP, parsing inicial e job consultável.
- Seed oficial via CLI/API.
- Fetch de URL oficial para DRE/EUR-Lex.
- Storage de bruto.
- Hash SHA-256.
- Parser inicial DRE/EUR-Lex.
- Chunking simples por artigo.
- Validação de source policy antes de `chat_ready`.
- Admin jobs para consultar progresso e erros.

Critério de aceitação:

- Um diploma oficial gera documento, bruto, chunks, job, SHA-256 e estado `pending_review` ou `chat_ready`.

### Milestone 5 — Embeddings e índice

Estado: **feito localmente com embeddings determinísticos e índice SQLite; providers externos pendentes para beta/produção**.

Entregáveis:

- Provider local determinístico para testes/demo.
- Tabela SQLite `legal_chunk_embeddings` por chunk.
- Indexação automática de chunks em ingestão e reindexação.
- Retrieval híbrido com fusão dense/sparse.
- Provider OpenAI/BGE embeddings.
- Adapter Pinecone/Qdrant.
- Reindexação quando modelo de embeddings/chunker muda.
- Fallback lexical preservado para testes determinísticos.

Critério de aceitação:

- `/retrieval/search` encontra chunks indexados.
- Se vector store falhar, o sistema abstém ou usa modo degradado explicitamente marcado; nunca inventa resposta.

### Milestone 6 — Rerank e evidence

Estado: **evidence feito localmente; Cohere Rerank pendente**.

Entregáveis:

- Adapter Cohere Rerank.
- Endpoint `/retrieval/rerank`.
- Endpoint `/evidence/build`.
- Citation labels.
- Warnings de consolidação.

Critério de aceitação:

- O LLM recebe evidência com metadados completos.

### Milestone 7 — Geração e validação

Estado: **feito localmente com gerador/validador determinísticos; prompts e providers externos pendentes**.

Entregáveis:

- Prompt gerador versionado.
- Prompt validador versionado.
- Endpoint `/answer/generate`.
- Endpoint `/answer/validate`.
- Veredictos `pass`, `abstain`, `fail`.
- Validação de URLs, artigos, processos, ECLI e CELEX contra evidência recuperada.
- Abstenção segura quando não há fonte suficiente.

Critério de aceitação:

- Artigo inventado causa `fail`.
- Falta de fonte causa `abstain`.

### Milestone 8 — Dify workflow

Estado: **workflow importável e UX jurídica mínima feitos; teste no ambiente Dify alvo pendente**.

Entregáveis:

- Workflow principal.
- HTTP nodes para API.
- Branching por veredicto.
- Exibição de fontes.
- Exibição de `audit_id`.
- Exibição de abstenção segura, avisos, confiança operacional e instrução de feedback.
- Smoke seed-to-chat executado antes da demo Dify.

Critério de aceitação:

- Utilizador recebe resposta validada ou abstenção.

### Milestone 9 — Avaliação e go-live

Estado: **suite mínima feita; expansão beta, Langfuse e deployment checklist final pendentes**.

Entregáveis:

- Evaluation suite mínima.
- Langfuse tracing.
- Deployment checklist preenchida.
- Runbook validado.

Critério de aceitação:

- Quality gate do MVP aprovado.

### Milestone 10 — Operação beta privada

Estado: **API operacional parcial feita; UI/admin dedicada, n8n e lista editorial pendentes**.

Entregáveis:

- n8n Manual URL ingestion.
- n8n Reindex schedule.
- n8n Evaluation run.
- Admin UI mínima.
- Feedback por resposta via API local.
- Lista editorial de jurisprudência selecionada.
- Runbook de incidentes exercitado em staging.
- Aprovação/rejeição/arquivo via Admin API com `change_note` obrigatório e blockers explícitos de `chat_ready`.
- Fila operacional via `/admin/documents/review-queue` com blockers e elegibilidade de promoção.
- Helper local `legal-review-queue` para consultar a mesma fila sem iniciar FastAPI.
- Helper local `legal-ingestion-jobs` para consultar jobs, erros e documentos associados sem iniciar FastAPI.
- Fila de triagem via `/admin/feedback/triage` e helper local `legal-feedback-triage` para exportar feedback negativo com contexto da auditoria.

Critério de aceitação:

- Um operador consegue ingerir, rever, promover/rejeitar, reindexar, auditar e avaliar sem acesso direto à base de dados.

### Milestone 11 — Produção comercial

Estado: **pendente**.

Entregáveis:

- PostgreSQL gerido ou self-hosted com migrations operacionalizadas.
- Object storage para bruto e artefactos.
- Backups e restore testado.
- Rate limiting, CORS restrito e TLS.
- Termos, privacidade, disclaimers e retenção de dados.
- Monitorização de custo, latência e falhas de providers.
- Autenticação, organizações e roles.

Critério de aceitação:

- O serviço pode entrar em beta paga sem respostas jurídicas sem fonte, sem identificadores críticos inventados e com auditoria completa.

## Testes mínimos

### Source policy

- Fonte Classe A permitida.
- Fonte discovery-only rejeitada como autoridade.
- Fonte bloqueada rejeitada.
- Fonte desconhecida rejeitada.

### Retrieval

- Query por artigo encontra artigo correto.
- Query com número de processo preserva número.
- Query com CELEX preserva identificador.

### Validação

- Resposta com artigo inventado falha.
- Resposta sem citação falha.
- Resposta com fonte não atual abstém.
- Resposta com fonte consolidada sem aviso falha ou é corrigida.

## Convenções de implementação

- Providers externos sempre atrás de adapters.
- Prompts versionados.
- Configuração sem segredos no repositório.
- Auditoria transacional.
- Abstenção segura como fallback.
- Sem fallback para conhecimento geral do modelo.
