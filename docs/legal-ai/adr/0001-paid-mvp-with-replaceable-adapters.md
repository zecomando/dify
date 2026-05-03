# ADR 0001 — Começar com MVP pago e adapters substituíveis

## Estado

Aceite.

## Contexto

O objetivo é chegar rapidamente a um MVP demonstrável e juridicamente credível. Ferramentas pagas como OpenAI embeddings, Cohere Rerank, Firecrawl, Tavily e Pinecone reduzem esforço operacional e aumentam qualidade inicial.

## Decisão

Construir o MVP com stack paga/acelerada, mas encapsular todos os vendors atrás de interfaces próprias.

## Consequências positivas

- Melhor qualidade no dia 1.
- Menor carga DevOps.
- Menor risco de demo fraca.
- Possibilidade de testar valor comercial cedo.

## Consequências negativas

- Dependência de vendors.
- Custos mensais.
- Necessidade de rever termos e privacidade.

## Mitigações

- Criar adapters substituíveis.
- Guardar dados em modelo próprio.
- Não acoplar lógica jurídica a vendor.
- Planear migração para Qdrant, Crawl4AI, BGE-M3 e modelos locais onde fizer sentido.
