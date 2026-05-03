# Risk register — Legal AI Chat

## Escala

- **Probabilidade:** Baixa, Média, Alta.
- **Impacto:** Baixo, Médio, Alto, Crítico.
- **Estado:** Aberto, Mitigado, Aceite, Fechado.

## R1 — Alucinação jurídica

- **Probabilidade:** Média
- **Impacto:** Crítico
- **Estado:** Aberto
- **Descrição:** o modelo inventa norma, artigo, processo, ECLI, CELEX ou conclusão.
- **Mitigação:** source policy em código, evidence builder, validador independente, fail em identificadores inventados, testes de alucinação.
- **Owner:** Engenharia + revisão jurídica.

## R2 — Uso de fonte não oficial como fundamento

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** domínios Classe A, discovery-only, bloqueio de domínios, validação antes de geração e antes da resposta final.

## R3 — Texto consolidado usado sem aviso

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** campo `is_consolidated`, warning obrigatório, validator check.

## R4 — Erro temporal ou versão errada

- **Probabilidade:** Alta
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** `is_current`, `version_date`, `effective_date`, archive de versões, abstenção em conflito temporal.

## R5 — Jurisprudência incompleta ou mal identificada

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** não promover sem tribunal, data, processo e URL; revisão humana para jurisprudência no MVP.

## R6 — Qualidade fraca de retrieval

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** pesquisa híbrida, rerank, evals, expected sources, ajuste de chunking.

## R7 — Crawling instável

- **Probabilidade:** Alta
- **Impacto:** Médio
- **Estado:** Aberto
- **Mitigação:** Firecrawl no MVP, fallback Crawl4AI, armazenamento bruto, hashes, retries.

## R8 — Custos de modelo escalam demasiado

- **Probabilidade:** Média
- **Impacto:** Médio
- **Estado:** Aberto
- **Mitigação:** monitorização diária, limites por tenant, caching, modelos mais baratos para classificação, batch embeddings.

## R9 — Dependência excessiva de vendors

- **Probabilidade:** Alta
- **Impacto:** Médio
- **Estado:** Aceite no MVP
- **Mitigação:** adapters próprios, plano Pinecone→Qdrant, OpenAI embeddings→BGE-M3, Firecrawl→Crawl4AI.

## R10 — Exposição de dados confidenciais

- **Probabilidade:** Média
- **Impacto:** Crítico
- **Estado:** Aberto
- **Mitigação:** políticas de privacidade, aviso ao utilizador, controlo de logs, DPA com vendors, zero retention quando aplicável.

## R11 — Falha de auditoria

- **Probabilidade:** Baixa
- **Impacto:** Crítico
- **Estado:** Aberto
- **Mitigação:** auditoria transacional, alerta se resposta sem audit log, smoke tests.

## R12 — Uso indevido como aconselhamento jurídico definitivo

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** disclaimers, modo estrito, confiança explícita, recomendação de validação por advogado em alto risco.

## R13 — Ingestão de grandes volumes sem autorização

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** respeitar termos de uso, limites de crawling, autorização IMPIC para grandes volumes BASE, preferir APIs oficiais.

## R14 — Ataques via prompt injection em documentos

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** tratar documentos como dados, não instruções; prompts anti-injection; sanitização; validação por evidência.

## R15 — SSRF ou abuso do crawler

- **Probabilidade:** Média
- **Impacto:** Alto
- **Estado:** Aberto
- **Mitigação:** allowlist de domínios, bloquear IPs privados, limitar redirects, timeouts e tamanho máximo.
