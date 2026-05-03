# Roadmap — Legal AI Chat

## Estratégia geral

Começar com a versão paga/acelerada para reduzir risco de qualidade e acelerar demonstração comercial. Depois substituir componentes pagos por alternativas open source onde isso não degrade a experiência jurídica.

## Roadmap de 24 horas

### 0h–2h — Setup

- Criar contas e chaves: OpenAI, Cohere, Pinecone, Tavily, Firecrawl, Langfuse.
- Subir FastAPI, PostgreSQL e Redis.
- Criar app Dify.
- Criar índice vetorial.

### 2h–4h — Fundação técnica

- Criar schema SQL inicial.
- Criar endpoints mínimos.
- Configurar embeddings.
- Configurar Cohere Rerank.
- Configurar Langfuse tracing.

### 4h–8h — Legislação inicial

- Ingerir diplomas nucleares.
- Chunking por artigo.
- Indexação vetorial.
- Promoção para `chat_ready`.

### 8h–12h — Jurisprudência inicial

- Ingerir decisões selecionadas.
- Extrair tribunal, data, processo e sumário.
- Classificar por área.
- Indexar.

### 12h–16h — Retrieval e evidência

- Implementar pesquisa híbrida.
- Implementar filtros por fonte, jurisdição e vigência.
- Implementar Evidence Builder.

### 16h–20h — Dify e validação

- Criar workflow Dify.
- Criar prompt do gerador.
- Criar endpoint de validação.
- Implementar abstenção.

### 20h–24h — Demo

- Testar 50 perguntas.
- Ajustar thresholds.
- Preparar script de demonstração.
- Ativar logs e auditoria.

## Roadmap de 72 horas

### Dia 1 — MVP funcional

- Chat jurídico.
- Legislação nuclear.
- Jurisprudência selecionada.
- Respostas com fontes.
- Validador.
- Abstenção.
- Auditoria.

### Dia 2 — Robustez

- n8n jobs.
- DRE watch.
- EUR-Lex refresh.
- DGSI watch.
- Reindex automático.
- Feedback do utilizador.
- Langfuse datasets.

### Dia 3 — Produto

- Painel admin mínimo.
- Gestão de fontes.
- Modos estrito, assistido e exploração.
- Export PDF.
- Vertical Contratação Pública.
- BASE/TED inicial.

## Roadmap de 30 dias

### Semana 1 — MVP privado

- Fechar arquitetura.
- Ingerir 50–80 diplomas.
- Ingerir 300–500 decisões.
- Criar dataset de avaliação.
- Testar com 2–3 advogados.

### Semana 2 — Qualidade jurídica

- Melhorar chunking.
- Melhorar citações.
- Adicionar verificação temporal.
- Adicionar deteção de conflitos entre versões.
- Expandir jurisprudência por área.
- Criar painel de auditoria.

### Semana 3 — Produto vendável

- Autenticação.
- Histórico de conversas.
- Exportação PDF/DOCX.
- Feedback por resposta.
- Gestão de clientes.
- Limites por plano.
- Modo escritório.

### Semana 4 — Beta controlada

- Beta fechada.
- Monitorização de custos.
- Backups.
- Termos e disclaimers.
- Política de privacidade.
- Relatórios de uso.
- Ajuste comercial.

## Roadmap de 90 dias

### Mês 1 — Qualidade e cobertura

- Expandir áreas jurídicas.
- Melhorar datasets.
- Criar score de confiança calibrado.
- Melhorar workflows de revisão humana.

### Mês 2 — Produto e monetização

- Planos comerciais.
- Billing.
- Multi-tenant.
- Exportação avançada.
- Relatórios jurídicos estruturados.

### Mês 3 — Soberania e otimização

- Migrar componentes selecionados para open source.
- Reduzir custo por resposta.
- Avaliar Qdrant Cloud/self-hosted.
- Avaliar BGE-M3 e BGE reranker.
- Manter premium onde houver maior impacto.

## Marco de go/no-go

O produto só deve entrar em beta paga se cumprir:

- Auditoria completa.
- Validação anti-alucinação ativa.
- Política de fontes aplicada em código.
- Abstenção correta em testes sem fonte.
- Zero identificadores críticos inventados nos testes de aceitação.
