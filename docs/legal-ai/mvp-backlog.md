# MVP backlog — Legal AI Chat

## Baseline local validada

O `legal-engine-api` já entrega um MVP local determinístico, auditável e sem dependência de providers externos:

- Source policy aplicada em código antes de qualquer promoção para `chat_ready`.
- Corpus inicial oficial seedável via `legal-seed` e `POST /admin/corpus/seed`.
- Ingestão manual com texto bruto, SHA-256, chunks por artigo, `legal_metadata` e jobs persistidos.
- Retrieval híbrido local com índice vetorial determinístico, lexical/sparse e filtros por jurisdição, área, tipo documental e vigência.
- Evidence builder com exclusão de fontes não oficiais e propagação de metadados jurídicos.
- Gerador/validador determinístico com bloqueio de URLs e identificadores inventados.
- Auditoria completa de respostas e runs de avaliação.
- Dify workflow importável para `/chat/answer`.
- Admin API para documentos, chunks, auditorias, seed, avaliação, reindexação e jobs.
- `legal-demo` para smoke local seed-to-chat.
- Quality gates locais verdes: `pytest`, `ruff check`, `ruff format --check`, `legal-eval` e `legal-demo`.

O backlog abaixo distingue:

- **feito localmente**: implementado e coberto por testes/evaluation no MVP determinístico.
- **pendente beta**: necessário para beta privada com corpus real e operação assistida.
- **pendente produção**: necessário para escala, segurança operacional, custo e produto comercial.

## P0 — Obrigatório para demo séria

### P0.1 — Source policy

**Objetivo:** impedir que fontes não oficiais sustentem respostas.

**Estado local:** implementado no `legal-engine-api` para validação de domínio, tipos documentais permitidos, metadados obrigatórios e identificadores obrigatórios por autoridade.

**Concluído localmente:**

- Criar lista Classe A.
- Criar lista discovery-only.
- Criar lista de domínios bloqueados.
- Implementar validação de domínio.
- Bloquear fundamentação com fontes não autorizadas.

**Pendente beta/produção:**

- Rever a source policy com jurista antes de beta privada.
- Definir processo de alteração/aprovação da policy.
- Adicionar alertas quando uma source policy nova mover documentos para `pending_review` ou `rejected`.

**Critério de aceitação:** uma fonte de blog ou escritório pode aparecer como discovery-only, mas nunca como base legal da resposta.

### P0.2 — Schema jurídico

**Objetivo:** guardar documentos, chunks e auditoria com metadados jurídicos.

**Estado local:** implementado em SQLite no `legal-engine-api`, incluindo `legal_metadata`, texto bruto, estados de ingestão, chunks, auditorias e runs de avaliação.

**Concluído localmente:**

- Criar `legal_documents`.
- Criar `legal_chunks`.
- Criar `answer_audits`.
- Criar jobs de ingestão/reindexação.
- Criar runs de avaliação.
- Criar estados de ingestão.
- Criar hashes SHA-256.
- Suporte mínimo a PostgreSQL via `LEGAL_ENGINE_DATABASE_URL`.
- Comandos operacionais `legal-db-migrate`, `legal-db-backup` e `legal-db-restore`.

**Pendente beta/produção:**

- Executar migração de staging para PostgreSQL gerido.
- Hardening de migrations versionadas para estratégia expand/contract.
- Definir retenção e agendamento de backups.
- Completar modelo temporal para cadeias de versões.

**Critério de aceitação:** cada chunk usado numa resposta é rastreável até documento, fonte, URL e versão.

### P0.3 — Ingestão de legislação

**Objetivo:** criar corpus inicial legislativo.

**Estado local:** ingestão manual/crawl inicial implementada com persistência de texto bruto, chunking determinístico, embeddings locais, reindexação a partir do bruto e promoção para `chat_ready` apenas quando há chunks e requisitos da source policy. Corpus inicial determinístico seedável via `legal-seed` e `POST /admin/corpus/seed` implementado para demo local. Corpus real ampliado de produção continua pendente.

**Concluído localmente:**

- Seed de diplomas PT.
- Seed de legislação UE.
- Chunking por artigo.
- Persistência de bruto.
- Promoção controlada por source policy.
- Reindexação local a partir do bruto.
- Embeddings locais determinísticos por chunk.

**Pendente beta/produção:**

- Hardening de fetch de URLs oficiais.
- Parsing automático robusto por fonte.
- Extração automática de metadados jurídicos.
- Embeddings externos.
- Vector store externo.

**Critério de aceitação:** perguntas sobre diplomas nucleares recuperam artigo correto e URL oficial.

### P0.4 — Retrieval híbrido

**Objetivo:** recuperar evidências juridicamente relevantes.

**Estado local:** retrieval híbrido local implementado com embeddings determinísticos em SQLite, fusão dense/sparse e filtros de jurisdição, tipo documental, vigência e área quando aplicável. Vector store externo e Cohere Rerank continuam pendentes.

**Concluído localmente:**

- Implementar lexical/sparse search.
- Implementar dense search local determinística.
- Fundir lexical + dense.
- Aplicar filtros.

**Pendente beta/produção:**

- Integrar embeddings externos.
- Integrar vector store externo.
- Integrar Cohere Rerank.
- Calibrar thresholds com evaluation suite expandida.

**Critério de aceitação:** artigos, números, alíneas, CELEX, ECLI e processos são preservados nos resultados.

### P0.5 — Evidence Builder

**Objetivo:** entregar ao LLM apenas contexto juridicamente utilizável.

**Estado local:** evidence builder local deduplica chunks, exclui fontes não oficiais, propaga `legal_metadata`, aplica requisitos da source policy e emite avisos de consolidação/vigência.

**Concluído localmente:**

- Agrupar chunks por documento.
- Deduplicar evidências.
- Criar citation labels.
- Marcar consolidação e vigência.
- Propagar `legal_metadata`.
- Excluir fontes que falham a source policy.

**Pendente beta/produção:**

- Separar legislação de jurisprudência.
- Adicionar apresentação UI consistente de avisos e confiança.
- Adicionar métricas de citation coverage.

**Critério de aceitação:** o gerador nunca recebe texto sem metadados de fonte.

### P0.6 — Gerador e validador

**Objetivo:** produzir resposta com fontes e bloquear alucinações.

**Estado local:** gerador determinístico local e validador implementados. O validador bloqueia URLs não recuperadas e identificadores jurídicos inventados, incluindo artigos, processos, ECLI e CELEX.

**Concluído localmente:**

- Implementar validação de citações.
- Implementar veredictos `pass`, `abstain`, `fail`.
- Gerar abstenção segura.

**Pendente beta/produção:**

- Criar prompt do gerador para provider LLM externo.
- Criar prompt do validador para provider LLM externo.
- Versionar prompts e associar versão a cada audit.
- Ativar validador independente do gerador em produção.

**Critério de aceitação:** artigo, processo, ECLI ou CELEX inventado causa `fail`.

### P0.7 — Dify workflow

**Objetivo:** disponibilizar chat funcional.

**Estado local:** workflow importável em `docs/legal-ai/dify-chat-answer.yml` apontado para `POST /chat/answer`, com perguntas sugeridas alinhadas ao corpus inicial, UX jurídica mínima para piloto, documentação de smoke em `dify-workflow.md` e estratégia de UI versionada em `docs/legal-ai/adr/0004-ui-strategy.md`. A demo local canónica é validada primeiro por `legal-smoke`, antes de depender da UI do Dify.

**Concluído localmente:**

- Criar workflow versionado importável.
- Apontar workflow para `POST /chat/answer`.
- Documentar smoke local antes da demo Dify.
- Alinhar perguntas sugeridas com corpus inicial.
- Comparar Dify, LibreChat, Open WebUI, AnythingLLM e UI própria em ADR versionada.
- Mostrar resposta validada, abstenção segura ou bloqueio do validador em secções estáveis.
- Mostrar fontes, versão, identificadores jurídicos, avisos, confiança operacional e instrução de feedback por `audit_id`.

**Pendente beta/produção:**

- Criar app Dify no ambiente alvo.
- Configurar base URL do `legal-engine-api` no ambiente alvo.
- Validar branch de resposta validada e branch de abstenção no Dify.
- Documentar variáveis por ambiente.
- Validar workflow após deploy de staging.
- Iniciar UI própria apenas se a beta exigir admin/revisão, histórico, roles, multi-tenant ou UX jurídica dedicada.

**Critério de aceitação:** utilizador recebe resposta final ou abstenção com auditoria associada.

### P0.8 — Auditoria

**Objetivo:** tornar cada resposta rastreável.

**Estado local:** auditoria de resposta e runs de avaliação persistidos no `legal-engine-api`.

**Concluído localmente:**

- Guardar query.
- Guardar retrieved chunks.
- Guardar reranked chunks.
- Guardar draft.
- Guardar validator report.
- Guardar final answer.

**Pendente beta/produção:**

- Guardar modelos, latência e custo.
- Ligar auditorias a sessões/conversas.
- Expor métricas agregadas para operação e qualidade.

**Critério de aceitação:** qualquer resposta pode ser reconstruída a partir do audit record.

## P1 — Necessário para beta privada

### P1.1 — Jurisprudência selecionada

**Estado local:** seeds demonstrativos oficiais existem para DGSI, Tribunal Constitucional, Curia/TJUE e HUDOC/TEDH, com metadados mínimos exigidos pela source policy. O crawl remoto já extrai metadados mínimos para estas fontes e mantém jurisprudência em `pending_review` até promoção explícita após revisão humana. Ainda faltam seleção editorial, UI/fila operacional de revisão e listas reais prioritárias.

**Próximas tarefas:**

- Definir lista inicial de 300–500 decisões por área prioritária.
- Criar critérios editoriais: tribunal, data, tema, relevância, estabilidade jurisprudencial.
- Definir fluxo operacional de aprovação/rejeição para promoção a `chat_ready`.
- Adicionar fila/UI para revisão humana sem acesso direto à base de dados.
- Expandir testes de preservação de ECLI e número de acórdão quando estes campos estiverem disponíveis no HTML real.

### P1.2 — n8n automations

**Estado local:** endpoints necessários para começar automações já existem parcialmente: `/ingestion/source`, `/ingestion/crawl-url`, `/admin/reindex`, `/admin/ingestion/jobs`, `/admin/evaluation/run` e `/admin/evaluation/runs`. Falta criar workflows n8n exportáveis e credenciais por ambiente.

**Próximas tarefas:**

- Criar workflow Manual URL ingestion com webhook interno e consulta de job.
- Criar workflow Reindex schedule com monitorização via `/admin/ingestion/jobs`.
- Criar workflow Evaluation run com alerta quando quality gate falha.
- Só depois criar DRE daily watch e EUR-Lex refresh com fetch remoto real.
- Criar política de retries, backoff, timeouts e alertas.

### P1.3 — Admin mínimo

**Estado local:** Admin API protegido por `X-Admin-Token` já permite listar documentos, consultar fila de revisão com blockers de promoção, consultar documento/chunks/texto bruto, promover/rejeitar/arquivar status com `change_note` obrigatório, validação da source policy e blockers explícitos para `chat_ready`, listar/consultar auditorias, correr/listar avaliações, seedar corpus, reindexar e consultar jobs. Operadores locais também conseguem usar `legal-review-queue` e `legal-ingestion-jobs` sem iniciar FastAPI.

**Próximas tarefas:**

- Criar UI admin mínima ou páginas internas Dify/console sobre a fila `/admin/documents/review-queue`.
- Adicionar ação de arquivar versão e manter cadeia temporal.
- Adicionar filtros por source, jurisdição, status, tipo documental e datas.
- Adicionar visualização UI de job error messages e documento associado; o CLI local já cobre esta consulta operacional.
- Restringir acesso admin por ambiente/role.
- Seguir a decisão de `docs/legal-ai/adr/0004-ui-strategy.md`: Dify não deve tornar-se admin canónico de produção se forem necessários workflows de revisão robustos.

### P1.4 — Evaluation suite

**Estado local:** evaluation suite mínima existe e passa com `legal-eval`, cobrindo perguntas canónicas, expected sources, no-source e hallucination guards. O tamanho ainda é insuficiente para beta privada.

**Próximas tarefas:**

- Expandir para 100 perguntas jurídicas por área.
- Criar 30 testes de alucinação com artigos, CELEX, ECLI, processos, datas e URLs falsos.
- Criar 20 testes de conflito temporal.
- Criar 20 testes sem fonte suficiente.
- Adicionar datasets Langfuse quando tracing estiver ativo.
- Bloquear deploy quando regressões críticas falharem.

### P1.5 — Feedback do utilizador

**Estado local:** implementado no MVP local com `answer_feedback` associado a `audit_id`, submissão em `POST /feedback/answer` e listagem/filtros admin em `GET /admin/feedback`.

**Próximas tarefas:**

- Expandir `rating` para categorias jurídicas operacionais se necessário.
- Suportar categorias: fonte errada, resposta incompleta, erro jurídico, resposta demasiado vaga.
- Expor endpoint protegido contra abuso.
- Criar export para revisão jurídica.

## P2 — Produto comercial

### P2.1 — Multi-tenant

- Organizações.
- Utilizadores.
- Roles.
- Limites por plano.

### P2.2 — Exportação

- PDF.
- DOCX.
- Relatório jurídico estruturado.
- Pacote de fontes.

### P2.3 — Contratação pública avançada

- BASE.
- TED.
- CPV.
- Entidades adjudicantes.
- Adjudicatários.
- Preços.
- Alertas.

### P2.4 — Comparação temporal

- Direito vigente.
- Direito à data.
- Diferenças entre versões.
- Cadeia de alterações.

## Definition of Done geral

Uma tarefa só está concluída quando:

- Está implementada.
- Tem teste ou avaliação manual documentada.
- Tem logging/auditoria quando aplicável.
- Respeita a source policy.
- Não introduz resposta jurídica sem fonte.
