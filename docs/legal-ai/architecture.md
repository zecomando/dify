# Arquitetura — Legal AI Chat

## Princípio arquitetural

A aplicação deve ser desenhada com adapters substituíveis. O MVP mantém um caminho local-first e determinístico para desenvolvimento, testes e operação mínima; providers pagos ou cloud podem acelerar qualidade e escala, mas cada dependência externa deve estar atrás de uma interface própria.

## Arquitetura lógica

```text
Utilizador
  ↓
Dify Chat / UI
  ↓
legal-engine-api
  ↓
Classificador jurídico
  ↓
Retriever híbrido
  ↓
Reranker
  ↓
Evidence Builder
  ↓
Gerador de resposta
  ↓
Validador anti-alucinação
  ↓
Resposta final com fontes ou abstenção
  ↓
Auditoria
```

## Arquitetura de ingestão

```text
Fontes oficiais
  ↓
Seed lists / Tavily / APIs oficiais
  ↓
Firecrawl / Fetchers próprios
  ↓
Docling / LlamaParse opcional
  ↓
Normalizer jurídico
  ↓
Chunker estrutural
  ↓
Embedding provider local ou OpenAI
  ↓
Vector store local, Pinecone ou Qdrant Cloud
  ↓
SQLite local / PostgreSQL metadata
  ↓
pending_review ou chat_ready
  ↓
Review Queue API/CLI
  ↓
promoção auditável para chat_ready
```

## Componentes

### Dify

Responsável por:

- Experiência de chat.
- Workflow visual.
- Chamada HTTP ao `legal-engine-api`.
- Exibição da resposta final.

Não deve ser responsável por:

- Política jurídica crítica.
- Decisão final de validade.
- Filtragem de fontes.
- Auditoria canónica.

### legal-engine-api

Serviço FastAPI próprio.

Responsável por:

- Classificação de área jurídica.
- Retrieval.
- Reranking.
- Construção de evidência.
- Validação anti-alucinação.
- Política de fontes.
- Auditoria.
- Ingestão e promoção de documentos.
- Review queue administrativa com blockers de promoção.

### SQLite local / PostgreSQL

Guarda:

- Documentos.
- Chunks.
- Estados de ingestão.
- Auditorias.
- Feedback.
- Runs de avaliação.
- Políticas versionadas.

### Vector store local / Pinecone / Qdrant Cloud

Guarda vetores e metadados indexáveis. O MVP local mantém um caminho determinístico sem cloud; Pinecone ou Qdrant Cloud são adapters de escala.

Índices recomendados:

- `legal_current`
- `legal_archive`
- `legal_cases`
- `procurement_data`

### Tavily

Usado apenas para descoberta de URLs.

Nunca deve ser fonte final de uma conclusão jurídica.

### Firecrawl

Usado para transformar URLs oficiais em Markdown limpo.

### Docling

Usado para parsing de PDFs, DOCX, HTML complexo e conversão estruturada.

### Embedding provider

O MVP local pode usar embeddings determinísticos para testes e operação mínima.

### OpenAI embeddings

Modelo recomendado:

- `text-embedding-3-large`

Alternativa mais barata:

- `text-embedding-3-small`

### Cohere Rerank

Usado para ordenar evidências por relevância semântica antes da geração.

### LLM gerador

Gera resposta provisória estritamente com base nas evidências.

### LLM validador

Modelo diferente do gerador, mais conservador.

Responsável por:

- Verificar afirmações jurídicas.
- Detetar citações inventadas.
- Remover conteúdo não suportado.
- Decidir `pass`, `abstain` ou `fail`.

### Langfuse

Responsável por:

- Tracing.
- Datasets.
- Avaliação.
- Custos.
- Latência.
- Debug de retrieval e prompts.

### n8n

Responsável por automações assíncronas:

- Monitorização DRE.
- Refresh EUR-Lex.
- Watch DGSI.
- Ingestão manual.
- Reindexação programada.
- Notificações administrativas.

## Interfaces internas obrigatórias

```text
EmbeddingProvider
RerankerProvider
CrawlerProvider
SearchDiscoveryProvider
VectorStore
LLMProvider
ValidatorProvider
ParserProvider
AuditStore
SourcePolicy
```

## Fluxo de resposta

1. Receber pergunta.
2. Normalizar idioma e intenção.
3. Classificar área jurídica, jurisdição e tipo de fonte necessária.
4. Definir filtros de retrieval.
5. Recuperar candidatos por pesquisa vetorial e lexical.
6. Aplicar source policy.
7. Rerank.
8. Construir evidência.
9. Gerar resposta provisória.
10. Validar resposta contra evidência.
11. Se `pass`, devolver resposta final.
12. Se `abstain` ou `fail`, devolver recusa fundamentada.
13. Guardar auditoria.

## Fluxo de ingestão

1. Receber URL, seed ou job agendado.
2. Validar domínio.
3. Extrair conteúdo.
4. Guardar bruto em storage.
5. Parsear.
6. Extrair metadados jurídicos.
7. Normalizar texto.
8. Criar chunks estruturais.
9. Gerar embeddings.
10. Indexar.
11. Validar qualidade.
12. Promover para `chat_ready` ou enviar para revisão.

## Fluxo de revisão humana

1. Documento entra em `pending_review` quando exige aprovação explícita ou falha alguma condição de promoção automática.
2. Operador consulta `GET /admin/documents/review-queue` ou `legal-review-queue`.
3. A fila calcula `promotion_blockers` com a mesma lógica usada pela promoção para `chat_ready`.
4. Legal reviewer consulta documento, chunks e texto bruto via Admin API quando necessário.
5. Data owner aprova, rejeita ou arquiva via `POST /admin/documents/{document_id}/status`.
6. Cada decisão exige `change_note` não vazio e fica refletida no documento.
7. Promoção bloqueada devolve blockers explícitos para correção antes de nova tentativa.

## Boundary de confiança

O sistema só deve confiar em:

- Domínios oficiais Classe A.
- Metadados extraídos ou verificados.
- Conteúdo guardado e versionado.
- Evidência entregue ao modelo no contexto.

O sistema não deve confiar em:

- Memória interna do LLM.
- Resultados brutos de pesquisa web.
- Fontes não oficiais.
- Citações geradas sem correspondência em chunks.

## Requisitos não funcionais iniciais

- Latência mediana abaixo de 12 segundos no MVP.
- Auditoria completa para 100% das respostas.
- Abstenção segura quando retrieval falha.
- Separação clara entre dados oficiais e discovery-only.
- Capacidade de reindexar corpus sem apagar auditorias antigas.
- Backups diários de PostgreSQL e storage.
