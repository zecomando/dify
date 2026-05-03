# Segurança, privacidade e compliance

## Âmbito

Este documento define controlos mínimos para operar um chat jurídico com dados potencialmente sensíveis e dependência de fontes oficiais.

## Princípios

- Minimização de dados.
- Separação por tenant.
- Auditoria integral.
- Controlo de acesso por função.
- Segredos fora do código.
- Validação de fontes em código.
- Respostas jurídicas apenas com evidência oficial.

## Dados tratados

### Dados de utilizador

- Perguntas.
- Histórico de conversas.
- Feedback.
- Identificador de sessão.
- Identificador de utilizador.

### Dados jurídicos

- Documentos oficiais.
- Chunks.
- Metadados jurídicos.
- Fontes.
- Versões.

### Dados operacionais

- Traces.
- Custos.
- Logs.
- Erros.
- Auditorias.

## Riscos de privacidade

- Utilizador inserir dados pessoais ou confidenciais.
- Envio de dados para providers externos.
- Exposição de auditorias.
- Mistura de dados entre clientes.
- Logs com informação sensível.

## Controlos mínimos

### Autenticação

- SSO ou autenticação forte para ambiente profissional.
- MFA para administradores.
- Tokens de API por ambiente.

### Autorização

Roles mínimos:

- `user`
- `legal_reviewer`
- `admin`
- `ops`
- `auditor`

### Segredos

- Nunca commitar chaves.
- Usar secret manager em produção.
- Rotação periódica.
- Chaves separadas por ambiente.

### Providers externos

Antes de produção:

- Rever termos de OpenAI/Claude/Cohere/Tavily/Firecrawl/Pinecone.
- Confirmar política de retenção de dados.
- Configurar zero data retention quando disponível e necessário.
- Evitar envio de documentos confidenciais para providers sem base contratual.

### Logs

- Não logar secrets.
- Redigir tokens.
- Limitar acesso a `answer_audits`.
- Separar logs técnicos de conteúdo de utilizador quando possível.

### RGPD

Checklist inicial:

- Base de licitude documentada.
- Política de privacidade.
- DPA com subprocessadores.
- Direito de acesso.
- Direito de apagamento quando aplicável.
- Retenção definida.
- Registo de atividades de tratamento.

## Disclaimers de produto

O produto deve informar que:

- Não substitui advogado.
- Não substitui consulta de fontes oficiais.
- Textos consolidados podem não ter valor jurídico autónomo.
- Respostas são apoio preliminar.
- Casos de alto risco exigem validação profissional.

## Segurança de ingestão

- Validar domínios antes de crawling.
- Bloquear SSRF.
- Limitar redirects.
- Limitar tamanho de ficheiros.
- Validar MIME types.
- Isolar parsing de documentos.
- Guardar hash.
- Não executar conteúdo descarregado.

## Segurança da API

- Rate limiting.
- API keys internas.
- CORS restrito.
- Validação de schemas.
- Timeouts.
- Retries controlados.
- Circuit breakers para providers.

## Segurança operacional

- Backups cifrados.
- TLS em produção.
- Rotação de logs.
- Least privilege em credenciais.
- Monitorização de erros críticos.
- Plano de incidentes.

## Go-live obrigatório

Não lançar em produção sem:

- Source policy ativa.
- Validador ativo.
- Auditoria ativa.
- Backups testados.
- Disclaimers visíveis.
- Política de privacidade.
- Controlo de acesso administrativo.
