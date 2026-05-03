# Retrieval, Evidence e Validação Anti-alucinação

## Objetivo

Garantir que o sistema só produz respostas jurídicas conclusivas quando existe evidência oficial suficiente, recuperada e validada.

## Política de retrieval

### Inputs mínimos

- Pergunta do utilizador.
- Jurisdição pretendida.
- Área jurídica detetada.
- Tipo de documento necessário.
- Modo de produto.
- Flag `current_only`.

### Estratégia

1. Classificar a pergunta.
2. Identificar se pede direito vigente, histórico, jurisprudência ou dados.
3. Aplicar filtros de fonte.
4. Executar pesquisa vetorial.
5. Executar pesquisa lexical/sparse.
6. Fundir candidatos.
7. Remover fontes não autorizadas.
8. Rerank.
9. Selecionar evidências finais.

## Configuração inicial

```yaml
retrieval:
  dense_top_k: 40
  sparse_top_k: 40
  rerank_top_n: 12
  final_context_chunks_min: 3
  final_context_chunks_max: 12
  min_relevance_score: 0.45
  current_only_default: true
  require_official_source: true
```

## Evidence Builder

### Responsabilidades

- Deduplicar chunks.
- Agrupar por documento.
- Ordenar por autoridade jurídica.
- Separar legislação, jurisprudência e dados.
- Construir labels de citação.
- Marcar avisos de consolidação.
- Marcar risco temporal.
- Remover evidência insuficiente.

### Campos obrigatórios de evidência

```yaml
evidence_item:
  chunk_id: string
  document_id: string
  source: string
  jurisdiction: string
  document_type: string
  title: string
  citation_label: string
  source_url: string
  canonical_url: string
  is_current: boolean
  is_consolidated: boolean
  legal_value_warning: string
  text: string
```

## Regras de geração

O gerador deve:

- Usar apenas evidência fornecida.
- Citar cada afirmação jurídica relevante.
- Distinguir norma, jurisprudência, facto, dado e inferência.
- Avisar quando usa texto consolidado.
- Não inventar artigos, processos, datas, CELEX, ECLI ou URLs.
- Abster-se quando a evidência é insuficiente.

## Regras de validação

O validador deve classificar cada afirmação como:

- `SUPPORTED`
- `PARTIALLY_SUPPORTED`
- `UNSUPPORTED`

### Fail obrigatório

`verdict = fail` quando:

- Existe artigo inventado.
- Existe número ou alínea inventada.
- Existe processo, ECLI ou CELEX inventado.
- Existe tribunal inventado.
- Existe URL não recuperado.
- Existe citação que não corresponde a evidência.
- A resposta usa fonte bloqueada como fundamento.

### Abstain obrigatório

`verdict = abstain` quando:

- Pergunta pede direito vigente e as fontes não estão marcadas como atuais.
- Há conflito temporal entre fontes.
- Há evidência insuficiente.
- A resposta final ficaria sem base jurídica suficiente.
- A fonte é apenas discovery-only.

### Pass permitido

`verdict = pass` apenas quando:

- Todas as afirmações jurídicas relevantes estão suportadas.
- As citações correspondem aos chunks.
- A source policy foi cumprida.
- Não há identificadores inventados.
- Os avisos obrigatórios estão presentes.

## Matriz de decisão

| Situação | Ação |
| --- | --- |
| Há lei atual + artigo exato | Responder |
| Há lei consolidada, mas sem ato original | Responder com aviso |
| Há jurisprudência sem tribunal/data/processo | Não usar como fundamento |
| Há fonte externa não oficial | Usar só para descoberta |
| Há conflito entre versões | Abster ou explicar conflito |
| Não há fontes suficientes | Recusar resposta conclusiva |
| Modelo menciona artigo não recuperado | Falhar validação |

## Confiança

### Alta

- Múltiplas fontes oficiais consistentes.
- Artigos ou identificadores exatos.
- Fonte atual.
- Sem conflito temporal.

### Média

- Fonte oficial suficiente, mas apenas consolidada.
- Pouca jurisprudência.
- Inferência moderada claramente assinalada.

### Baixa

- Evidência limitada.
- Risco temporal.
- Jurisprudência escassa.
- Deve tender para resposta cautelosa ou abstenção.

## Logs obrigatórios

- Query original.
- Query normalizada.
- Área detetada.
- Filtros aplicados.
- Resultados recuperados.
- Resultados reranked.
- Evidência final.
- Draft answer.
- Validator report.
- Final answer.
- Veredicto.
- Modelos.
- Latência.
- Custo.
