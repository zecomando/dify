# Production runbook — Legal AI Chat

## Objetivo

Definir procedimentos operacionais para manter o serviço disponível, seguro, auditável e juridicamente controlado.

## Ambientes

- `local`
- `staging`
- `production`

## Serviços críticos

- Dify.
- `legal-engine-api`.
- PostgreSQL.
- Redis.
- Pinecone/Qdrant Cloud.
- Object storage.
- Langfuse.
- n8n.
- Providers LLM/embeddings/rerank/crawl.

## Deploy

### Pré-deploy

- Executar testes unitários.
- Executar evaluation suite mínima.
- Confirmar migrations.
- Confirmar source policy.
- Confirmar `.env` de ambiente.
- Confirmar backups recentes.

### Execução de deploy

- Fazer deploy em staging.
- Executar smoke tests.
- Executar 10 perguntas canónicas.
- Verificar Langfuse traces.
- Promover para produção.

### Pós-deploy

- Monitorizar logs por 30 minutos.
- Verificar latência.
- Verificar custos.
- Verificar abstenções anómalas.
- Verificar falhas de provider.

## Smoke tests

- Health check.
- Pergunta simples sobre artigo conhecido.
- Pergunta que deve abster.
- Pergunta com identificador falso.
- Pergunta com fonte consolidada.
- Consulta de audit record.

## Backups

### PostgreSQL

- Backup diário.
- Retenção mínima de 30 dias.
- Teste de restore mensal.

### Object storage

- Versioning ativo.
- Lifecycle policy documentada.
- Retenção de raw documents.

### Configurações

- Export de workflows Dify.
- Export de workflows n8n.
- Source policy versionada.
- Prompts versionados.

## Incidentes

### Incidente: validador indisponível

Ação:

- Ativar modo degradado seguro.
- Bloquear respostas conclusivas.
- Devolver abstenção temporária.
- Alertar equipa.

### Incidente: vector DB indisponível

Ação:

- Bloquear geração.
- Devolver mensagem de indisponibilidade.
- Não fazer fallback para conhecimento do modelo.

### Incidente: provider LLM indisponível

Ação:

- Usar fallback configurado se cumprir política.
- Se não houver fallback, devolver indisponibilidade.

### Incidente: source policy corrompida ou ausente

Ação:

- Bloquear respostas jurídicas.
- Colocar serviço em manutenção parcial.
- Restaurar versão anterior.

### Incidente: alucinação crítica detetada em produção

Ação:

- Marcar audit record.
- Retirar resposta da UI se aplicável.
- Criar regression test.
- Rever retrieval/evidence/validator.
- Reexecutar evaluation suite.
- Comunicar utilizadores afetados se necessário.

## Manutenção regular

### Diária

- Verificar jobs de ingestão.
- Verificar custos.
- Verificar alertas.
- Verificar falhas de validação.

### Semanal

- Executar evaluation suite.
- Rever feedback negativo.
- Rever documentos em `pending_review`.
- Rever fontes com alterações.

### Mensal

- Testar restore.
- Rever vendors e custos.
- Rever política de retenção.
- Rever source policy.
- Atualizar datasets.

## Rollback

Rollback deve incluir:

- Código.
- Prompts.
- Source policy.
- Configuração de retrieval.
- Modelo/reranker se alterado.

## Modo degradado seguro

Quando algum componente crítico falha, o sistema deve preferir abstenção a resposta sem fonte.

Mensagem padrão:

> O serviço não consegue validar a resposta com segurança neste momento. Por isso, não devo fornecer uma conclusão jurídica.
