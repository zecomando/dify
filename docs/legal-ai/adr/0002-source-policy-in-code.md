# ADR 0002 — Source policy em código, não apenas em prompt

## Estado

Aceite.

## Contexto

Prompts não são garantia suficiente para impedir fontes inválidas. Um sistema jurídico precisa de controlo determinístico sobre que fontes podem fundamentar respostas.

## Decisão

Implementar a política de fontes em código e em configuração versionada, usando `source-policy.yml` como artefacto canónico.

## Consequências positivas

- Bloqueio determinístico de fontes não oficiais.
- Auditoria clara.
- Menor risco de alucinação por fonte externa.
- Possibilidade de testes automatizados.

## Consequências negativas

- Mais engenharia.
- Necessidade de manter allowlist atualizada.

## Mitigações

- Revisão periódica da policy.
- Testes automáticos para domínios Classe A, discovery-only e bloqueados.
- Processo formal para adicionar fontes.
