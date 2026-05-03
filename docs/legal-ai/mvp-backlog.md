# MVP backlog — Legal AI Chat

## P0 — Obrigatório para demo séria

### P0.1 — Source policy

**Objetivo:** impedir que fontes não oficiais sustentem respostas.

**Tarefas:**

- Criar lista Classe A.
- Criar lista discovery-only.
- Criar lista de domínios bloqueados.
- Implementar validação de domínio.
- Bloquear fundamentação com fontes não autorizadas.

**Critério de aceitação:** uma fonte de blog ou escritório pode aparecer como discovery-only, mas nunca como base legal da resposta.

### P0.2 — Schema jurídico

**Objetivo:** guardar documentos, chunks e auditoria com metadados jurídicos.

**Tarefas:**

- Criar `legal_documents`.
- Criar `legal_chunks`.
- Criar `answer_audits`.
- Criar estados de ingestão.
- Criar hashes SHA-256.

**Critério de aceitação:** cada chunk usado numa resposta é rastreável até documento, fonte, URL e versão.

### P0.3 — Ingestão de legislação

**Objetivo:** criar corpus inicial legislativo.

**Tarefas:**

- Seed de diplomas PT.
- Seed de legislação UE.
- Fetch de URLs oficiais.
- Parsing.
- Chunking por artigo.
- Embeddings.
- Indexação.

**Critério de aceitação:** perguntas sobre diplomas nucleares recuperam artigo correto e URL oficial.

### P0.4 — Retrieval híbrido

**Objetivo:** recuperar evidências juridicamente relevantes.

**Tarefas:**

- Implementar dense search.
- Implementar lexical/sparse search.
- Fundir resultados.
- Aplicar filtros.
- Integrar Cohere Rerank.

**Critério de aceitação:** artigos, números, alíneas, CELEX, ECLI e processos são preservados nos resultados.

### P0.5 — Evidence Builder

**Objetivo:** entregar ao LLM apenas contexto juridicamente utilizável.

**Tarefas:**

- Agrupar chunks por documento.
- Deduplicar evidências.
- Criar citation labels.
- Marcar consolidação e vigência.
- Separar legislação de jurisprudência.

**Critério de aceitação:** o gerador nunca recebe texto sem metadados de fonte.

### P0.6 — Gerador e validador

**Objetivo:** produzir resposta com fontes e bloquear alucinações.

**Tarefas:**

- Criar prompt do gerador.
- Criar prompt do validador.
- Implementar validação de citações.
- Implementar veredictos `pass`, `abstain`, `fail`.
- Gerar abstenção segura.

**Critério de aceitação:** artigo, processo, ECLI ou CELEX inventado causa `fail`.

### P0.7 — Dify workflow

**Objetivo:** disponibilizar chat funcional.

**Tarefas:**

- Criar app Dify.
- Criar nodes HTTP para FastAPI.
- Criar LLM node de draft answer.
- Criar branch por veredicto.
- Mostrar fontes e confiança.

**Critério de aceitação:** utilizador recebe resposta final ou abstenção com auditoria associada.

### P0.8 — Auditoria

**Objetivo:** tornar cada resposta rastreável.

**Tarefas:**

- Guardar query.
- Guardar retrieved chunks.
- Guardar reranked chunks.
- Guardar draft.
- Guardar validator report.
- Guardar final answer.
- Guardar modelos, latência e custo.

**Critério de aceitação:** qualquer resposta pode ser reconstruída a partir do audit record.

## P1 — Necessário para beta privada

### P1.1 — Jurisprudência selecionada

- DGSI.
- Tribunal Constitucional.
- Curia/TJUE.
- HUDOC/TEDH.
- Aprovação humana mínima.

### P1.2 — n8n automations

- DRE daily watch.
- EUR-Lex refresh.
- DGSI weekly watch.
- Manual URL ingestion.
- Reindex schedule.

### P1.3 — Admin mínimo

- Ver documentos.
- Promover/rejeitar fontes.
- Ver auditorias.
- Reprocessar documento.
- Marcar versão como arquivada.

### P1.4 — Evaluation suite

- 100 perguntas jurídicas.
- 30 testes de alucinação.
- 20 testes de conflito temporal.
- 20 testes sem fonte suficiente.

### P1.5 — Feedback do utilizador

- Útil/não útil.
- Fonte errada.
- Resposta incompleta.
- Reportar erro jurídico.

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
