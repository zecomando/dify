# Operating model — Legal AI Chat

## Objetivo

Definir papéis, responsabilidades e rotinas para desenvolver, validar e operar o chat jurídico.

## Papéis

### Product owner

Responsável por:

- Priorizar áreas jurídicas.
- Definir modos de produto.
- Validar proposta de valor.
- Coordenar beta com utilizadores.

### Tech lead

Responsável por:

- Arquitetura.
- Interfaces de providers.
- Qualidade de código.
- Segurança técnica.
- Go-live técnico.

### Legal reviewer

Responsável por:

- Rever fontes críticas.
- Aprovar jurisprudência selecionada.
- Validar respostas de benchmark.
- Rever disclaimers e limites de produto.

### Data/ingestion owner

Responsável por:

- Seed lists.
- Pipelines de ingestão.
- Qualidade de metadados.
- Gestão de versões.

### Ops owner

Responsável por:

- Deploy.
- Backups.
- Monitorização.
- Incidentes.
- Custos.

## RACI resumido

| Atividade | Product | Tech | Legal | Data | Ops |
| --- | --- | --- | --- | --- | --- |
| Source policy | A | R | R | C | C |
| Ingestão legislação | C | R | C | A/R | C |
| Ingestão jurisprudência | C | C | A/R | R | C |
| Prompts | C | R | A/R | C | I |
| Evaluation suite | C | R | A/R | R | I |
| Deploy produção | I | A/R | C | C | R |
| Incidente jurídico | C | R | A/R | C | C |
| Incidente técnico | I | A/R | C | C | R |

## Rotinas

### Diária durante MVP

- Rever falhas de ingestão.
- Rever 10 respostas auditadas.
- Rever custos.
- Rever erros de provider.

### Semanal

- Executar evaluation suite.
- Rever feedback negativo.
- Promover/rejeitar documentos pendentes.
- Rever source policy.
- Atualizar backlog.

### Mensal

- Rever risco jurídico.
- Rever vendors e custos.
- Testar restore.
- Rever qualidade por área jurídica.
- Decidir substituições open source.

## Processo de aprovação de fontes

1. Fonte entra como `pending_review`.
2. Sistema valida domínio e metadados.
3. Legal reviewer aprova ou rejeita.
4. Data owner promove para `chat_ready`.
5. Auditoria regista decisão.

## Processo de incidente jurídico

1. Marcar resposta como suspeita.
2. Bloquear reutilização em exemplos ou cache.
3. Rever evidência e validator report.
4. Criar teste de regressão.
5. Corrigir fonte, retrieval, prompt ou validador.
6. Reexecutar evaluation suite.
7. Comunicar se houver utilizador afetado.

## Critério de maturidade

O produto só deve escalar comercialmente quando:

- Há legal reviewer responsável.
- Há evaluation suite recorrente.
- Há incident process.
- Há audit trail completo.
- Há source policy versionada.
