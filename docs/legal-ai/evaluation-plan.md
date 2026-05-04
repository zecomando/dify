# Plano de avaliação — Legal AI Chat

## Objetivo

Medir se o sistema responde apenas quando tem evidência oficial suficiente, se cita corretamente e se se abstém quando deve.

## Princípios

- Avaliar retrieval, geração e validação separadamente.
- Medir acertos e recusas corretas.
- Testar perguntas reais e perguntas-armadilha.
- Não lançar em produção sem quality gates mínimos.
- Guardar todos os runs para comparação histórica.

## Datasets iniciais

```yaml
eval_dataset:
  legal_questions: 100
  hallucination_tests: 30
  temporal_conflict_tests: 20
  no_source_tests: 20
  citation_tests: 30
```

## Dataset local versionado

O dataset determinístico atual em `docs/legal-ai/evals/` contém 33 casos:

- `benchmark_50_questions.jsonl`: 18 perguntas canónicas com fontes esperadas.
- `expected_sources.jsonl`: 13 mapeamentos explícitos de domínio/fonte esperada.
- `no_source_tests.jsonl`: 7 perguntas que devem abster sem corpus suficiente.
- `hallucination_tests.jsonl`: 8 regressões contra identificadores jurídicos inventados.

A cobertura local inclui DRE, EUR-Lex, DGSI, Tribunal Constitucional, Curia/TJUE, HUDOC/CEDH, TED e BASE, alinhada com o corpus seedado do MVP.

## Tipos de teste

### Perguntas de artigo

Objetivo: verificar se o sistema encontra artigo, número e alínea corretos.

Exemplo:

> Quais são os fundamentos de exclusão de propostas no CCP?

### Perguntas de aplicação

Objetivo: verificar se o sistema aplica a norma com cautela.

Exemplo:

> Uma proposta pode ser excluída por preço anormalmente baixo sem pedido de esclarecimentos?

### Perguntas de jurisprudência

Objetivo: verificar se decisões têm tribunal, data, processo e fonte.

Exemplo:

> Há jurisprudência sobre exclusão de propostas por incumprimento de requisitos técnicos?

### Perguntas temporais

Objetivo: verificar direito vigente vs direito à data.

Exemplo:

> Qual era o regime aplicável antes da alteração de determinado diploma?

### Perguntas sem fonte suficiente

Objetivo: confirmar abstenção.

Exemplo:

> Qual é a interpretação definitiva dos tribunais sobre uma questão sem corpus suficiente?

### Perguntas-armadilha

Objetivo: detetar alucinações.

Exemplo:

> Explica o artigo 999.º do Código dos Contratos Públicos.

## Métricas

### Retrieval

- `retrieval_recall_at_12`
- `source_precision`
- `official_domain_rate`
- `current_source_rate`
- `citation_candidate_accuracy`

### Geração

- `citation_coverage`
- `unsupported_legal_claim_rate`
- `hallucinated_identifier_rate`
- `consolidation_warning_rate`
- `answer_completeness_score`

### Validação

- `validator_false_pass_rate`
- `validator_correct_abstention_rate`
- `validator_fail_on_fake_identifier_rate`
- `validator_missing_citation_detection_rate`

### Produto

- `median_latency_ms`
- `p95_latency_ms`
- `cost_per_answer`
- `user_helpful_rate`
- `reported_legal_error_rate`

## Quality gates do MVP

```yaml
mvp_quality_gate:
  source_precision: ">= 90%"
  official_domain_rate: "100% for strict mode"
  hallucinated_identifier_rate: "0 critical cases"
  unsupported_legal_claim_rate: "<= 5%"
  correct_abstention_on_no_source: ">= 90%"
  validator_fail_on_fake_identifier_rate: ">= 95%"
  median_latency_ms: "<= 12000"
```

## Quality gates de beta paga

```yaml
paid_beta_quality_gate:
  source_precision: ">= 95%"
  official_domain_rate: "100% for strict mode"
  hallucinated_identifier_rate: "0"
  unsupported_legal_claim_rate: "<= 2%"
  correct_abstention_on_no_source: ">= 95%"
  p95_latency_ms: "<= 25000"
  audit_coverage: "100%"
```

## Processo de avaliação

1. Selecionar dataset.
2. Executar perguntas em modo estrito.
3. Guardar `answer_audits`.
4. Comparar fontes esperadas.
5. Rever respostas falhadas.
6. Classificar erros.
7. Ajustar retrieval, prompts ou source policy.
8. Reexecutar regressão.

## Execução automatizada atual

O `legal-engine-api` executa gates determinísticos locais sem LLMs nem rede:

```bash
uv run --project legal-engine-api legal-eval
uv run --project legal-engine-api legal-eval --json
```

O mesmo runner pode ser executado e persistido via API:

```http
POST /admin/evaluation/run
GET /admin/evaluation/runs/{run_id}
```

O histórico persistido inclui métricas, quality gates e casos falhados. O workflow `.github/workflows/legal-engine-api.yml` executa `ruff`, `pytest` e `uv run --project legal-engine-api legal-eval` em alterações de `legal-engine-api/**` e `docs/legal-ai/**`.

Estado validado localmente: `passed=True`, `total=33`, `failed=0`.

## Classificação de erros

- `retrieval_miss`
- `wrong_source`
- `non_official_source_used`
- `missing_citation`
- `unsupported_claim`
- `hallucinated_identifier`
- `wrong_temporal_scope`
- `validator_false_pass`
- `validator_false_fail`
- `latency_timeout`

## Regressão obrigatória

Executar antes de:

- Alterar chunker.
- Alterar embeddings.
- Alterar reranker.
- Alterar prompts.
- Alterar modelo gerador.
- Alterar modelo validador.
- Promover grande lote de documentos.
- Fazer deploy de produção.
