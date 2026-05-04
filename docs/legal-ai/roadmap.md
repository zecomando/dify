# Roadmap — Legal AI Chat

## Estratégia geral

Começar pelo MVP local determinístico já validado, aumentar cobertura jurídica com ingestão oficial controlada e só depois introduzir providers externos, automações, UI admin e escala comercial.

A regra de produto mantém-se: nenhuma resposta jurídica conclusiva pode sair sem fonte oficial elegível, evidência rastreável e auditoria.

## Estado atual

O `legal-engine-api` já cobre a demo técnica local:

- Source policy aplicada em runtime.
- Corpus inicial oficial seedável.
- Ingestão manual/local com texto bruto, SHA-256, chunks e jobs.
- Retrieval híbrido local com embeddings determinísticos, lexical/sparse e filtros jurídicos.
- Evidence builder com metadados e exclusão de fontes inválidas.
- Gerador/validador determinístico com abstenção segura.
- Auditoria completa.
- Evaluation suite mínima com quality gate verde.
- Dify workflow importável.
- Admin API para documentos, chunks, auditorias, evaluations, seed, reindex e jobs.

Principais gaps para beta:

- Hardening de fetch/parsing remoto.
- Providers externos de embeddings, vector store e rerank.
- Hardening de migrations PostgreSQL para produção.
- n8n workflows exportáveis.
- UI admin mínima.
- UI/admin mínima para feedback do utilizador.
- Corpus real ampliado e avaliação expandida.

## Próximo sprint técnico

### Bloco 1 — Sincronização e operação local

Objetivo: deixar a demo e a operação local totalmente reproduzíveis.

- Manter `pytest`, `ruff check`, `ruff format --check`, `legal-eval` e `legal-demo` como gate obrigatório.
- Importar o workflow Dify em ambiente alvo e validar com corpus seedado.
- Criar n8n workflow `Local/staging seed smoke`.
- Documentar variáveis de ambiente por ambiente.
- Atualizar checklist de deploy com resultados da última validação.

Critério de saída:

- Uma máquina limpa consegue subir API, semear corpus, correr `legal-demo`, importar Dify e obter resposta com `audit_id`.

### Bloco 2 — Fetch/parsing oficial inicial

Objetivo: substituir seeds manuais por ingestão real controlada, começando por fontes legislativas.

- Implementar fetch HTTP com timeout, retries, user-agent e limites.
- Implementar fetch/parsing DRE para HTML consolidado simples.
- Implementar fetch/parsing EUR-Lex por CELEX.
- Guardar bruto antes de parsing.
- Persistir metadados extraídos automaticamente.
- Manter documentos extraídos em `pending_review` quando houver incerteza.

Critério de saída:

- Uma URL DRE e um CELEX reais geram documento, bruto, SHA-256, chunks, metadados mínimos e job auditável.

### Bloco 3 — Embeddings e retrieval híbrido

Objetivo: aproximar retrieval de beta sem perder determinismo nos testes.

- Criar interface `EmbeddingProvider`.
- Implementar provider local determinístico de embeddings.
- Persistir embeddings por chunk em SQLite.
- Implementar fusão lexical + dense.
- Manter fallback lexical para testes e modo degradado.
- Preparar adapter OpenAI/BGE embeddings e Pinecone/Qdrant para staging.

Critério de saída:

- `/retrieval/search` recupera evidências por dense local e lexical; em staging, se o vector store externo falhar, o sistema abstém ou degrada explicitamente sem inventar.

### Bloco 4 — n8n mínimo operacional

Objetivo: retirar tarefas repetitivas do operador sem pôr n8n no caminho crítico do chat.

- Manual URL ingestion.
- Reindex schedule.
- Evaluation run.
- Alertas para jobs `rejected` e quality gates falhados.
- Export dos workflows sem segredos.

Critério de saída:

- Um operador consegue ingerir uma fonte, consultar job, reindexar e executar evaluation sem tocar diretamente na base de dados.

## Roadmap de 72 horas

### Dia 1 — Staging reproduzível

- Subir `legal-engine-api` em staging com secret `LEGAL_ENGINE_ADMIN_TOKEN`.
- Executar `legal-db-migrate` na base persistente do ambiente.
- Semear corpus inicial.
- Importar Dify workflow.
- Executar smoke via `legal-demo`, Dify e `/admin/evaluation/run`.
- Ativar n8n seed smoke e evaluation run.
- Produzir relatório de smoke com `audit_id` e `evaluation_run_id`.

### Dia 2 — Ingestão real controlada

- Implementar fetch/parsing DRE inicial.
- Implementar fetch/parsing EUR-Lex inicial.
- Criar lista de diplomas/CELEX monitorizados.
- Adicionar n8n Manual URL ingestion.
- Validar que documentos reais entram em `pending_review` ou `chat_ready` conforme policy.
- Adicionar testes de regressão para parsing e metadados.

### Dia 3 — Retrieval beta e revisão humana

- Adicionar embeddings/vector store em ambiente staging.
- Implementar retrieval híbrido.
- Criar fila/processo de revisão humana para jurisprudência.
- Adicionar endpoint ou fluxo de rejeição com motivo.
- Validar 50 perguntas canónicas.
- Abrir UI/admin mínima ou runbook operacional para revisão.

## Roadmap de 30 dias

### Semana 1 — MVP privado

- Fechar arquitetura de providers: crawler, parser, embeddings, vector store, rerank e LLM.
- Migrar staging para `LEGAL_ENGINE_DATABASE_URL` quando houver base PostgreSQL disponível.
- Ingerir 50–80 diplomas/atos oficiais com metadados mínimos.
- Ingerir jurisprudência apenas selecionada e revista.
- Expandir evaluation suite para pelo menos 100 perguntas.
- Testar com 2–3 juristas/advogados em sessões acompanhadas.

### Semana 2 — Qualidade jurídica

- Melhorar chunking.
- Melhorar citações.
- Adicionar verificação temporal.
- Adicionar deteção de conflitos entre versões.
- Expandir jurisprudência por área.
- Criar painel de auditoria.
- Calibrar thresholds de retrieval/rerank com base em evaluation failures.
- Criar casos de regressão para cada erro jurídico encontrado.

### Semana 3 — Produto vendável

- Autenticação.
- Histórico de conversas.
- Exportação PDF/DOCX.
- UI para feedback por resposta.
- Gestão de clientes.
- Limites por plano.
- Modo escritório.
- Admin UI para documentos, jobs, auditorias, evaluations e feedback.
- Disclaimers e termos visíveis no fluxo do utilizador.

### Semana 4 — Beta controlada

- Beta fechada.
- Monitorização de custos.
- Backups.
- Termos e disclaimers.
- Política de privacidade.
- Relatórios de uso.
- Ajuste comercial.
- Exercício de restore.
- Exercício de incidente: provider indisponível, vector store indisponível e validador indisponível.
- Go/no-go com checklist preenchida.

## Roadmap de 90 dias

### Mês 1 — Qualidade e cobertura

- Expandir áreas jurídicas.
- Melhorar datasets.
- Criar score de confiança calibrado.
- Melhorar workflows de revisão humana.
- Atingir cobertura mínima por área prioritária com fontes oficiais.
- Criar métricas por área: source precision, abstention rate, hallucination guard e citation coverage.

### Mês 2 — Produto e monetização

- Planos comerciais.
- Billing.
- Multi-tenant.
- Exportação avançada.
- Relatórios jurídicos estruturados.
- Roles por organização.
- Auditoria acessível por admin autorizado.
- Limites de uso por plano.

### Mês 3 — Soberania e otimização

- Migrar componentes selecionados para open source.
- Reduzir custo por resposta.
- Avaliar Qdrant Cloud/self-hosted.
- Avaliar BGE-M3 e BGE reranker.
- Manter premium onde houver maior impacto.
- Comparar custo/qualidade entre providers pagos e open source com a mesma evaluation suite.
- Manter rollback para providers premium quando quality gates degradarem.

## Marco de go/no-go

O produto só deve entrar em beta paga se cumprir:

- Auditoria completa.
- Validação anti-alucinação ativa.
- Política de fontes aplicada em código.
- Abstenção correta em testes sem fonte.
- Zero identificadores críticos inventados nos testes de aceitação.
- Corpus beta com fontes oficiais reais, não apenas seeds demonstrativos.
- Operador consegue rever, rejeitar, promover e reindexar sem acesso direto à base de dados.
- Backups e restore testados.
- Termos, privacidade e disclaimers aprovados.
