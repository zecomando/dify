# Observabilidade e auditoria

## Objetivo

Garantir rastreabilidade completa de cada resposta, permitindo depuração técnica, revisão jurídica, análise de custos e melhoria contínua.

## Princípio

Se uma resposta não puder ser auditada, não deve ser usada em produção.

## Ferramentas

- **Langfuse:** tracing de prompts, modelos, retrieval, tokens, custos e datasets.
- **PostgreSQL:** auditoria canónica persistente.
- **Helicone:** gateway opcional para roteamento, custos e fallback de modelos.
- **Grafana/Prometheus:** métricas operacionais quando o serviço amadurecer.

## Eventos obrigatórios

### Query received

Campos:

- `session_id`
- `user_id`
- `query`
- `mode`
- `timestamp`

### Query classified

Campos:

- `jurisdiction`
- `area`
- `document_types`
- `current_only`
- `query_rewrite`

### Retrieval completed

Campos:

- `dense_top_k`
- `sparse_top_k`
- `filters`
- `candidate_count`
- `official_domain_count`
- `retrieved_chunks`

### Rerank completed

Campos:

- `reranker_model`
- `top_n`
- `reranked_chunks`
- `scores`

### Evidence built

Campos:

- `evidence_count`
- `documents_used`
- `sources_used`
- `consolidation_warnings`
- `temporal_risks`

### Draft generated

Campos:

- `generator_model`
- `prompt_version`
- `input_tokens`
- `output_tokens`
- `latency_ms`
- `estimated_cost`

### Validation completed

Campos:

- `validator_model`
- `verdict`
- `unsupported_claims`
- `missing_citations`
- `hallucinated_identifiers`
- `wrong_version_risk`

### Final answer returned

Campos:

- `final_answer`
- `confidence`
- `abstained`
- `latency_ms`
- `answer_audit_id`

## Audit record obrigatório

Cada resposta deve guardar:

- Pergunta original.
- Pergunta normalizada.
- Classificação.
- Filtros.
- Chunks recuperados.
- Chunks reranked.
- Evidência final.
- Resposta provisória.
- Relatório do validador.
- Resposta final.
- Veredicto.
- Modelos usados.
- Custos.
- Latência.

## Métricas operacionais

- `requests_total`
- `answers_pass_total`
- `answers_abstain_total`
- `answers_fail_total`
- `retrieval_empty_total`
- `validator_fail_total`
- `hallucinated_identifier_total`
- `latency_p50_ms`
- `latency_p95_ms`
- `cost_per_answer_usd`
- `provider_error_rate`

## Alertas

### Críticos

- Validador indisponível.
- Source policy não carregada.
- Base de dados indisponível.
- Vector DB indisponível.
- Resposta sem audit log.
- Identificador inventado passou validação.

### Avisos

- Aumento de abstenções.
- Aumento de custo por resposta.
- Aumento de latência p95.
- Queda de source precision.
- Falhas em jobs de ingestão.

## Retenção

### Produção inicial

- Audit logs: 1 ano, salvo política diferente.
- Traces detalhados: 90 dias.
- Documentos oficiais processados: indefinido.
- Raw fetched documents: indefinido ou conforme storage/custo.
- Feedback: 1 ano.

## Privacidade

Dados pessoais em queries devem ser tratados como sensíveis.

Recomendações:

- Redação opcional de PII antes de enviar para providers externos.
- Aviso ao utilizador para não inserir dados confidenciais desnecessários.
- Separação por tenant.
- Controlo de acesso a auditorias.
