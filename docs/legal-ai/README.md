# Legal AI Chat — Artefactos end-to-end

Este diretório contém os artefactos de produto, arquitetura, engenharia, segurança, avaliação e produção para construir um chat jurídico baseado em fontes oficiais.

## Princípio fundamental

O sistema não é uma IA que sabe Direito. É um assistente que só responde juridicamente quando consegue provar a resposta com fontes oficiais recuperadas, citadas e validadas.

## Artefactos principais

- **`product-brief.md`** — visão, posicionamento, escopo e modos de produto.
- **`architecture.md`** — arquitetura técnica end-to-end da versão paga/acelerada.
- **`roadmap.md`** — plano por 24h, 72h, 30 dias e evolução para soberania.
- **`mvp-backlog.md`** — backlog priorizado por fases e critérios de aceitação.
- **`source-policy.yml`** — política de fontes oficiais, discovery-only e bloqueios.
- **`api-contracts.openapi.yml`** — contratos iniciais da `legal-engine-api`.
- **`data-model.sql`** — modelo relacional mínimo para documentos, chunks e auditoria.
- **`prompts.md`** — prompts-base do classificador, gerador e validador.
- **`ingestion-plan.md`** — pipelines de ingestão para DRE, EUR-Lex, DGSI, Curia, HUDOC, BASE e TED.
- **`retrieval-validation-policy.md`** — política de retrieval, evidence building e anti-alucinação.
- **`dify-workflow.md`** — desenho do workflow principal em Dify.
- **`adr/0004-ui-strategy.md`** — matriz e decisão sobre Dify, alternativas open source e UI própria.
- **`n8n-workflows.md`** — automações assíncronas de ingestão e monitorização.
- **`evaluation-plan.md`** — plano de qualidade, datasets, métricas e gates.
- **`observability-and-audit.md`** — tracing, auditoria e monitorização operacional.
- **`security-privacy-compliance.md`** — segurança, privacidade, RGPD e controlos jurídicos.
- **`production-runbook.md`** — operação, incidentes, backups e manutenção.
- **`deployment-checklist.md`** — checklist de entrada em produção.
- **`risk-register.md`** — riscos principais e mitigação.
- **`cost-and-vendor-strategy.md`** — orçamento, vendors e estratégia de substituição.
- **`.env.example`** — variáveis de ambiente esperadas para o MVP.

## Subdiretórios

- **`seeds/`** — listas iniciais de diplomas, legislação UE e queries de jurisprudência.
- **`evals/`** — perguntas de benchmark e testes de alucinação.
- **`adr/`** — decisões arquiteturais relevantes.

## Regra de produção

Uma resposta jurídica só pode sair como conclusiva se cumprir todos os requisitos seguintes:

- **Fonte oficial permitida**.
- **Evidência recuperada pelo sistema**.
- **Citação por afirmação jurídica relevante**.
- **Validação anti-alucinação aprovada**.
- **Ausência de conflito temporal não resolvido**.
- **Auditoria completa guardada**.

Se algum requisito falhar, o sistema deve abster-se ou responder apenas em modo exploratório, sem conclusão jurídica.

## Implementação local atual

A implementação local vive em `legal-engine-api/` e fornece:

- **Pipeline orquestrado** em `POST /chat/answer`.
- **Workflow Dify importável** em `dify-chat-answer.yml`.
- **Estratégia de UI versionada** em `adr/0004-ui-strategy.md`: Dify para piloto/beta curta e UI própria para produção robusta se a beta validar.
- **Admin mínimo protegido por `X-Admin-Token`** para documentos, chunks, jobs, auditorias, feedback e avaliações.
- **Corpus inicial determinístico** via CLI `legal-seed` ou `POST /admin/corpus/seed`.
- **Auditoria de respostas** em `GET /admin/audit/{answer_id}` e feedback por resposta em `POST /feedback/answer`.
- **Quality gates determinísticos** via CLI `uv run --project legal-engine-api legal-eval`.
- **Execução persistida de avaliações** em `POST /admin/evaluation/run`.
- **Consulta histórica de avaliações** em `GET /admin/evaluation/runs/{run_id}`.

## Staging mínimo

1. Definir `LEGAL_ENGINE_ADMIN_TOKEN` com um valor secreto por ambiente.
2. Subir `legal-engine-api` com `docker compose up --build` a partir de `legal-engine-api/`.
3. Confirmar `GET /health`.
4. Ingerir corpus inicial via `uv run --project legal-engine-api legal-seed` ou `POST /admin/corpus/seed`.
5. Confirmar documentos em `/admin/documents` enviando `X-Admin-Token`.
6. Importar `dify-chat-answer.yml` no Dify e validar o HTTP node para `/chat/answer`.
7. Executar smoke Dify com pergunta respondível, pergunta-armadilha e pergunta sem corpus suficiente.

## Quality gates em CI

O workflow `.github/workflows/legal-engine-api.yml` valida alterações em `legal-engine-api/**` e `docs/legal-ai/**` com:

- `ruff check`
- `ruff format --check`
- `pytest`
- `uv run --project legal-engine-api legal-eval`
