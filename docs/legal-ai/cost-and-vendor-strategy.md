# Custos e estratégia de vendors

## Objetivo

Acelerar o MVP com ferramentas pagas, mantendo arquitetura preparada para substituição futura por alternativas open source ou self-hosted.

## Stack paga inicial

```yaml
paid_mvp:
  orchestration: Dify Cloud or self-hosted
  backend: FastAPI
  database: PostgreSQL
  queue: Redis
  vector_db: Pinecone
  discovery: Tavily
  crawling: Firecrawl
  parser: Docling
  embeddings: OpenAI text-embedding-3-large
  reranker: Cohere Rerank
  generator: OpenAI or Claude
  validator: different model/provider
  observability: Langfuse
  automation: n8n
```

## Estimativa mensal MVP

| Componente | Estimativa |
| --- | ---: |
| VPS / cloud app | 40–90 € |
| Pinecone | 50–100 USD |
| Firecrawl | 16–83 USD |
| Tavily | 0–30+ USD |
| OpenAI embeddings | baixo no MVP |
| Geração + validação | 30–150 € |
| Cohere Rerank | 10–50 € |
| Storage | 5–20 € |
| Langfuse | self-hosted ou cloud |

## Total provável

```text
150–350 €/mês para MVP sério
```

## Onde pagar no início

### Alta prioridade

- Reranking premium.
- Modelo gerador forte.
- Modelo validador forte.
- Embeddings multilingues de qualidade.
- Crawling robusto.

### Baixa prioridade

- UI custom completa.
- Painéis sofisticados.
- Modelos locais.
- Infra self-hosted complexa.

## Estratégia de adapters

Cada vendor deve estar atrás de interface própria:

```text
EmbeddingProvider
RerankerProvider
CrawlerProvider
VectorStore
LLMProvider
DiscoveryProvider
ParserProvider
```

## Plano de substituição

### Fase 1 — Após MVP validado

- Pinecone → Qdrant Cloud.
- Firecrawl → Crawl4AI para fontes estáveis.
- Tavily → discovery próprio para fontes conhecidas.

### Fase 2 — Otimização de custo

- OpenAI embeddings → BGE-M3 em corpus menos crítico.
- Cohere Rerank → BGE Reranker em tarefas de baixo risco.
- Classificador com modelo barato.

### Fase 3 — Soberania parcial

- Qdrant self-hosted.
- Langfuse self-hosted.
- n8n self-hosted.
- Modelos locais para tarefas internas.

## Regras de controlo de custos

- Guardar custo estimado por resposta.
- Definir budget diário.
- Alertar se custo sobe acima de limiar.
- Usar caching para queries repetidas.
- Limitar `top_k` e contexto.
- Usar batch embeddings.
- Não fazer crawling sem limite explícito.

## Decisão recomendada

Para entrada rápida no mercado:

- Usar ferramentas pagas no MVP.
- Manter interfaces próprias.
- Migrar apenas quando houver métricas reais de custo/qualidade.

A prioridade inicial é provar qualidade jurídica e confiança, não otimizar custos prematuramente.
