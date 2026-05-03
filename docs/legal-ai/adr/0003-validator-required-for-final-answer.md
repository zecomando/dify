# ADR 0003 — Validador obrigatório antes da resposta final

## Estado

Aceite.

## Contexto

O gerador pode produzir texto plausível mas não suportado. Em domínio jurídico, identificadores inventados ou conclusões sem fonte são risco crítico.

## Decisão

Toda resposta jurídica conclusiva deve passar por um validador anti-alucinação antes de ser mostrada como final.

## Regras

- O validador deve usar apenas evidência recuperada.
- O modelo validador deve ser diferente do gerador.
- `fail` bloqueia resposta.
- `abstain` devolve recusa fundamentada.
- Falha técnica do validador ativa modo degradado seguro.

## Consequências positivas

- Redução de alucinações.
- Rastreabilidade.
- Maior confiança para advogados.

## Consequências negativas

- Mais latência.
- Mais custo por resposta.
- Possíveis falsos negativos.

## Mitigações

- Usar modelos mais baratos em perguntas simples quando maduro.
- Otimizar evidência.
- Medir validator false fail rate.
