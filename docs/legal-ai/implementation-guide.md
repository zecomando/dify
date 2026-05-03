# Guia de implementação — Legal AI Chat

## Objetivo

Transformar os artefactos deste diretório numa implementação incremental, segura e testável.

## Ordem recomendada

1. Criar `legal-engine-api`.
2. Implementar source policy em código.
3. Criar schema PostgreSQL.
4. Implementar ingestão mínima.
5. Implementar chunking legislativo.
6. Implementar embeddings e vector store.
7. Implementar retrieval híbrido.
8. Implementar evidence builder.
9. Implementar geração e validação.
10. Integrar Dify.
11. Ativar auditoria e Langfuse.
12. Executar evaluation suite.

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

## Implementação por milestone

### Milestone 1 — API mínima

Entregáveis:

- FastAPI com `/health`.
- Configuração por ambiente.
- Autenticação simples por API key interna.
- Logging estruturado.

Critério de aceitação:

- Serviço arranca localmente.
- `/health` responde `ok`.

### Milestone 2 — Source policy

Entregáveis:

- Loader de `source-policy.yml`.
- Validador de domínio.
- Função `can_ground_answer(url, document_type)`.
- Testes para Classe A, discovery-only e bloqueados.

Critério de aceitação:

- Blog ou escritório nunca pode fundamentar resposta.

### Milestone 3 — Dados e auditoria

Entregáveis:

- Migrations para `data-model.sql`.
- Repositórios para documentos, chunks e auditorias.
- Criação de `answer_audits` em todas as respostas.

Critério de aceitação:

- Nenhuma resposta sai sem audit record.

### Milestone 4 — Ingestão mínima

Entregáveis:

- Endpoint `/ingestion/source`.
- Fetch de URL oficial.
- Storage de bruto.
- Hash SHA-256.
- Parser inicial.
- Chunking simples por artigo.

Critério de aceitação:

- Um diploma oficial gera documento, chunks e estado `chunked`.

### Milestone 5 — Embeddings e índice

Entregáveis:

- Provider OpenAI embeddings.
- Adapter Pinecone.
- Indexação de chunks.
- Guardar `vector_id`.

Critério de aceitação:

- `/retrieval/search` encontra chunks indexados.

### Milestone 6 — Rerank e evidence

Entregáveis:

- Adapter Cohere Rerank.
- Endpoint `/retrieval/rerank`.
- Endpoint `/evidence/build`.
- Citation labels.
- Warnings de consolidação.

Critério de aceitação:

- O LLM recebe evidência com metadados completos.

### Milestone 7 — Geração e validação

Entregáveis:

- Prompt gerador versionado.
- Prompt validador versionado.
- Endpoint `/answer/generate`.
- Endpoint `/answer/validate`.
- Veredictos `pass`, `abstain`, `fail`.

Critério de aceitação:

- Artigo inventado causa `fail`.
- Falta de fonte causa `abstain`.

### Milestone 8 — Dify workflow

Entregáveis:

- Workflow principal.
- HTTP nodes para API.
- Branching por veredicto.
- Exibição de fontes.

Critério de aceitação:

- Utilizador recebe resposta validada ou abstenção.

### Milestone 9 — Avaliação e go-live

Entregáveis:

- Evaluation suite mínima.
- Langfuse tracing.
- Deployment checklist preenchida.
- Runbook validado.

Critério de aceitação:

- Quality gate do MVP aprovado.

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
