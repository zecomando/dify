# Product brief — Legal AI Chat

## Visão

Construir um assistente jurídico para Direito português, Direito da União Europeia e CEDH que responda apenas quando consiga sustentar a resposta em fontes oficiais recuperadas, citadas e validadas.

## Posicionamento

O produto deve ser posicionado como uma camada de apoio à investigação e preparação jurídica, não como substituto de advogado, tribunal, autoridade pública ou consulta oficial.

## Tese de produto

A vantagem competitiva não é o modelo generativo. A vantagem competitiva é o pipeline controlado de fontes, evidência, validação, auditoria e abstenção.

## Público-alvo inicial

- **Advogados:** pesquisa rápida com fontes e citações.
- **Sociedades de advogados:** triagem e preparação de pareceres preliminares.
- **Juristas internos:** apoio a compliance e interpretação preliminar.
- **Consultores de contratação pública:** pesquisa sobre CCP, BASE, TED e jurisprudência.
- **Equipas públicas:** apoio documental sem substituir validação formal.

## Escopo inicial recomendado

- **Contratação Pública**
- **Direito Administrativo**
- **Direito Civil essencial**
- **Direito Laboral essencial**
- **Direito Fiscal essencial**
- **Direito da União Europeia relacionado**
- **CEDH/TEDH quando aplicável**

## Não objetivos do MVP

- **Não emitir pareceres jurídicos definitivos.**
- **Não substituir consulta dos atos originais.**
- **Não usar blogs ou escritórios como fundamento jurídico.**
- **Não responder com conhecimento geral quando a pergunta exige direito aplicável.**
- **Não cobrir todo o Direito com profundidade igual no primeiro MVP.**

## Modos de produto

### Modo Estrito

Modo default para uso profissional.

- Usa apenas corpus `chat_ready`.
- Usa apenas fontes oficiais Classe A.
- Exige `is_current=true` para perguntas sobre direito vigente.
- Exige citações por afirmação jurídica relevante.
- Abstem-se quando não há evidência suficiente.

### Modo Assistido

Modo de investigação controlada.

- Usa corpus `chat_ready`.
- Pode usar Tavily/Firecrawl em domínios permitidos.
- Pode marcar fontes novas como `pending_review`.
- Só permite conclusão final se houver fonte oficial validada.

### Modo Exploração

Modo de descoberta não conclusiva.

- Pode usar fontes externas separadas.
- Não permite conclusão jurídica final.
- Deve etiquetar todo conteúdo externo como não validado.

## Promessa ao utilizador

- Respostas claras.
- Fontes oficiais visíveis.
- Citações rastreáveis.
- Avisos sobre consolidação.
- Confiança explícita.
- Recusa quando o sistema não consegue provar.

## Formato de resposta final

1. **Resposta curta**
2. **Base legal**
3. **Jurisprudência relevante**
4. **Aplicação ao caso**
5. **Limites / incertezas**
6. **Fontes**
7. **Confiança**

## Mensagem de abstenção padrão

Não consigo confirmar com segurança uma resposta jurídica conclusiva nas fontes oficiais disponíveis. Posso indicar as fontes encontradas e sugerir uma pesquisa adicional, mas não devo formular uma conclusão jurídica sem suporte suficiente.

## Critérios de sucesso do MVP

- Responder a perguntas simples de legislação com fonte correta.
- Citar artigos, números e alíneas sem inventar identificadores.
- Abster-se corretamente em perguntas sem fonte suficiente.
- Separar legislação, jurisprudência e inferência.
- Registar auditoria completa de cada resposta.
- Permitir demonstração convincente a advogados em menos de 72 horas.
