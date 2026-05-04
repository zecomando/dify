# Dify workflow — Chat jurídico

## Objetivo

Usar Dify como interface de chat, mantendo a decisão jurídica crítica no `legal-engine-api`.

O workflow Dify não deve gerar nem validar direito. Deve apenas:

- receber a pergunta do utilizador;
- chamar `POST /chat/answer`;
- mostrar a resposta final já validada;
- mostrar fontes, avisos, veredicto e `audit_id`.

## Artefacto importável

O DSL inicial está em:

```text
docs/legal-ai/dify-chat-answer.yml
```

Este ficheiro cria uma app Dify em modo `advanced-chat` com:

```text
Start
  ↓
HTTP Node: POST /chat/answer
  ↓
Code Node: formatar resposta segura
  ↓
Answer Node
```

## URL do `legal-engine-api`

O DSL usa por defeito:

```text
http://host.docker.internal:8000/chat/answer
```

Usar esta URL quando o Dify corre em Docker e o `legal-engine-api` corre no host.

Se o Dify e o `legal-engine-api` correrem diretamente no host, alterar o HTTP node para:

```text
http://127.0.0.1:8000/chat/answer
```

Se ambos correrem na mesma rede Docker Compose, usar o nome do serviço:

```text
http://legal-engine-api:8000/chat/answer
```

## Payload enviado ao backend

```json
{
  "question": "{{#sys.query#}}",
  "mode": "strict",
  "current_only": true,
  "top_k_dense": 40,
  "top_k_sparse": 40,
  "top_n": 8
}
```

O workflow Dify não usa `X-Admin-Token`, porque chama apenas `/chat/answer`. O token é obrigatório só para endpoints `/admin/*`, usados em operação, auditoria e avaliação.

## Output esperado de `/chat/answer`

O Dify deve tratar estes campos como canónicos:

- `answer`
- `verdict`
- `audit_id`
- `evidence`
- `warnings`
- `unsupported_claims`
- `missing_citations`
- `hallucinated_identifiers`

O campo `answer` já é a resposta final segura. O Dify não deve mostrar qualquer draft.

## Regras de UI

- Mostrar sempre `answer`.
- Mostrar `verdict`.
- Mostrar `audit_id`.
- Mostrar fontes oficiais a partir de `evidence`.
- Mostrar `warnings` quando existirem.
- Não mostrar raciocínio interno.
- Não gerar resposta alternativa no Dify.
- Não chamar LLM node para responder juridicamente.

## Branching

O DSL inicial não usa branching visual porque `/chat/answer` já devolve uma resposta final segura para `pass`, `abstain` e `fail`.

Mais tarde, se for útil para UX, pode-se adicionar IF/ELSE apenas para apresentação:

- `verdict = pass`: mostrar resposta e fontes;
- `verdict = abstain`: destacar abstenção segura;
- `verdict = fail`: destacar falha de validação e não mostrar qualquer draft.

A regra mantém-se: a decisão jurídica final vem sempre do backend.

## Importação manual no Dify

1. Definir `LEGAL_ENGINE_ADMIN_TOKEN`.
2. Semear o corpus inicial com `uv run --project legal-engine-api legal-seed` ou `POST /admin/corpus/seed`.
3. Validar o backend local com `uv run --project legal-engine-api legal-demo`.
4. Abrir Dify.
5. Escolher importação de app por YAML/DSL.
6. Importar `docs/legal-ai/dify-chat-answer.yml`.
7. Confirmar a URL do HTTP node.
8. Garantir que o `legal-engine-api` está acessível.
9. Testar uma pergunta com fonte oficial.
10. Testar uma pergunta sem corpus suficiente que deve abster.

## Smoke tests recomendados

Pergunta que deve responder com fonte:

```text
Quais são os pressupostos da responsabilidade civil extracontratual?
```

Pergunta europeia que deve responder com fonte:

```text
No RGPD da União Europeia, quais são as bases de licitude para tratamento de dados pessoais?
```

Pergunta sem corpus suficiente:

```text
Qual é a interpretação definitiva dos tribunais sobre uma questão que ainda não foi indexada?
```

## Princípio de substituição

O Dify deve ser substituível por outra UI. Por isso, source policy, evidence building, geração final, validação anti-alucinação e auditoria canónica ficam no `legal-engine-api`, não no workflow visual.
