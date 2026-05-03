# Deployment checklist — Legal AI Chat

## Objetivo

Checklist obrigatória para entrada em staging, beta privada e produção.

## 1. Produto

- [ ] Modo Estrito é o default.
- [ ] UI mostra fontes oficiais.
- [ ] UI mostra confiança.
- [ ] UI mostra aviso de consolidação quando aplicável.
- [ ] UI permite feedback do utilizador.
- [ ] UI não mostra draft answer quando validação falha.
- [ ] Disclaimer jurídico está visível.
- [ ] Mensagem de abstenção é clara.

## 2. Source policy

- [ ] `source-policy.yml` está carregada em runtime.
- [ ] Domínios Classe A podem fundamentar resposta.
- [ ] Domínios discovery-only não podem fundamentar resposta.
- [ ] Domínios bloqueados nunca aparecem como autoridade.
- [ ] Fonte desconhecida causa abstenção ou rejeição.
- [ ] Consolidação DRE/EUR-Lex gera aviso obrigatório.

## 3. Ingestão

- [ ] Documentos brutos são guardados em storage.
- [ ] Hash SHA-256 é calculado.
- [ ] Metadados jurídicos mínimos são extraídos.
- [ ] Chunks são não vazios.
- [ ] Embeddings são criados.
- [ ] Documento só vira `chat_ready` após validação.
- [ ] Versões antigas são arquivadas, não apagadas.

## 4. Retrieval

- [ ] Pesquisa vetorial funciona.
- [ ] Pesquisa lexical/sparse funciona ou está explicitamente planeada.
- [ ] Filtros por jurisdição funcionam.
- [ ] Filtros por tipo documental funcionam.
- [ ] Filtro `current_only` funciona.
- [ ] Cohere Rerank está integrado.
- [ ] Empty retrieval gera abstenção.

## 5. Geração

- [ ] Temperatura do gerador está em `0.0`.
- [ ] Prompt proíbe conhecimento externo.
- [ ] Prompt exige citações.
- [ ] Prompt exige aviso sobre consolidação.
- [ ] Prompt distingue norma, jurisprudência, dado e inferência.

## 6. Validação

- [ ] Modelo validador é diferente do gerador.
- [ ] Validador recebe evidências e metadados.
- [ ] Artigo inventado causa `fail`.
- [ ] Processo/ECLI/CELEX inventado causa `fail`.
- [ ] Fonte não atual em pergunta de direito vigente causa `abstain`.
- [ ] Fonte discovery-only causa `abstain` para conclusão jurídica.
- [ ] Resposta sem citações causa `fail` ou `abstain`.

## 7. Auditoria

- [ ] 100% das respostas têm `answer_audit`.
- [ ] Retrieved chunks são guardados.
- [ ] Reranked chunks são guardados.
- [ ] Draft answer é guardado.
- [ ] Validator report é guardado.
- [ ] Final answer é guardado.
- [ ] Modelos, custo e latência são guardados.

## 8. Observabilidade

- [ ] Langfuse recebe traces.
- [ ] Erros de provider são logados.
- [ ] Latência p50/p95 é monitorizada.
- [ ] Custo por resposta é estimado.
- [ ] Alertas críticos estão configurados.

## 9. Segurança

- [ ] Secrets não estão no repositório.
- [ ] `.env.example` não contém credenciais reais.
- [ ] API interna tem autenticação.
- [ ] Admin endpoints são protegidos.
- [ ] Rate limiting está configurado.
- [ ] CORS é restrito.
- [ ] TLS está ativo em produção.
- [ ] Backups estão cifrados.

## 10. RGPD e jurídico

- [ ] Política de privacidade pronta.
- [ ] Termos de uso prontos.
- [ ] Disclaimers jurídicos prontos.
- [ ] Retenção de dados definida.
- [ ] Subprocessadores documentados.
- [ ] Acesso a auditorias é restrito.

## 11. Avaliação

- [ ] Evaluation suite mínima executada.
- [ ] Perguntas de alucinação executadas.
- [ ] Perguntas sem fonte suficiente executadas.
- [ ] Perguntas de conflito temporal executadas.
- [ ] Quality gate do MVP aprovado.
- [ ] Regressões críticas têm testes.

## 12. Backups e recuperação

- [ ] Backup PostgreSQL diário ativo.
- [ ] Restore testado.
- [ ] Storage com versioning.
- [ ] Workflows Dify exportados.
- [ ] Workflows n8n exportados.
- [ ] Source policy versionada.

## 13. Go/no-go

### Go

- [ ] Zero identificadores críticos inventados nos testes.
- [ ] Auditoria 100% ativa.
- [ ] Validador ativo.
- [ ] Source policy ativa em código.
- [ ] Abstenção segura funciona.

### No-go

- [ ] Sistema responde sem fonte oficial.
- [ ] Sistema permite fonte bloqueada como autoridade.
- [ ] Validador indisponível não bloqueia resposta.
- [ ] Auditoria falha silenciosamente.
- [ ] Backups não testados.
