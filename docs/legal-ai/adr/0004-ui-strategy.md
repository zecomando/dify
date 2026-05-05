# ADR 0004 — Estratégia de UI para piloto, beta e produção

## Estado

Aceite.

## Contexto

O `legal-engine-api` concentra a decisão jurídica crítica: source policy, retrieval, evidence builder, geração final segura, validação anti-alucinação e auditoria canónica. A UI deve ser substituível e não pode gerar nem validar direito fora deste backend.

O projeto já tem um workflow Dify importável em `docs/legal-ai/dify-chat-answer.yml`, suficiente para piloto acompanhado. Para beta privada e produção robusta, a UI também precisa suportar fontes oficiais visíveis, `audit_id`, feedback por resposta, histórico, autenticação, roles, revisão humana, admin operacional e multi-tenant.

## Critérios de decisão

Pontuação: 1 fraco, 3 aceitável, 5 forte.

| Critério | Peso | Dify | LibreChat | Open WebUI | AnythingLLM | UI própria Next.js/shadcn |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Chat funcional rápido | 5 | 5 | 4 | 4 | 4 | 2 |
| Chamada limpa a `legal-engine-api` | 5 | 5 | 3 | 3 | 3 | 5 |
| Bloqueio de geração fora do backend | 5 | 4 | 2 | 2 | 2 | 5 |
| Fontes, avisos, veredicto e `audit_id` | 5 | 3 | 2 | 2 | 2 | 5 |
| Feedback por resposta ligado a auditoria | 4 | 2 | 2 | 2 | 2 | 5 |
| Admin/revisão de documentos e jobs | 5 | 2 | 1 | 1 | 1 | 5 |
| Autenticação, roles e multi-tenant jurídico | 5 | 3 | 3 | 2 | 2 | 5 |
| Customização UX jurídica | 4 | 3 | 2 | 2 | 2 | 5 |
| Operação local-first/self-hosted | 4 | 4 | 4 | 4 | 4 | 4 |
| Custo de implementação inicial | 3 | 5 | 4 | 4 | 4 | 1 |
| Manutenção de longo prazo | 4 | 3 | 3 | 3 | 3 | 4 |

## Resultado ponderado

| Opção | Resultado | Leitura |
| --- | ---: | --- |
| Dify | 174 | Melhor para piloto e beta curta; limita admin/UX jurídica profunda. |
| LibreChat | 119 | Bom chat genérico, mas fraco para pipeline jurídico canónico e admin. |
| Open WebUI | 111 | Útil para modelos locais, mas desalinhado com auditoria jurídica/produto. |
| AnythingLLM | 111 | Simples para RAG, mas duplica responsabilidades que já vivem no backend. |
| UI própria Next.js/shadcn | 198 | Melhor para produção robusta; maior custo inicial. |

## Decisão

Usar estratégia em duas etapas:

1. **Piloto e beta curta:** manter Dify como UI principal, porque já existe workflow importável e permite validar o motor jurídico rapidamente.
2. **Produção robusta:** preparar UI própria em Next.js/shadcn se a beta validar valor com advogados e se forem necessários admin, revisão, feedback, histórico, roles, multi-tenant e UX jurídica dedicada.

LibreChat, Open WebUI e AnythingLLM não devem ser adotados como UI principal do produto jurídico. Podem ser usados apenas para protótipos internos ou benchmarks pontuais se houver uma hipótese concreta a testar.

## Regras obrigatórias para qualquer UI

- Chamar `POST /chat/answer` como fonte canónica da resposta final.
- Mostrar apenas `answer` final, nunca draft interno.
- Mostrar `verdict`, `audit_id`, fontes oficiais, avisos e confiança.
- Expor abstenção como resultado seguro, não como erro de produto.
- Enviar feedback para `POST /feedback/answer` associado ao `audit_id`.
- Não permitir que a UI use um LLM próprio para formular resposta jurídica conclusiva.
- Proteger endpoints administrativos fora do fluxo público de chat.

## Consequências positivas

- Mantém velocidade de piloto com Dify.
- Evita reconstruir UI antes de validar qualidade jurídica.
- Preserva caminho claro para produto profissional e vendável.
- Mantém a lógica jurídica fora da UI.

## Consequências negativas

- Pode haver trabalho duplicado se o Dify for muito customizado antes da UI própria.
- A UI própria exige investimento em frontend, autenticação, roles e operação.
- Dify pode limitar a experiência de revisão humana/admin durante a beta.

## Mitigações

- Limitar customizações Dify ao necessário para piloto: resposta, fontes, avisos, `audit_id` e feedback.
- Manter contrato do backend estável para trocar UI sem reescrever lógica jurídica.
- Só iniciar UI própria depois de critérios de beta estarem claros.
- Usar componentes existentes do workspace Dify quando fizer sentido, mas sem acoplar a política jurídica ao frontend.

## Critérios para iniciar UI própria

Iniciar UI própria quando pelo menos três condições forem verdadeiras:

- Advogados em beta pedem histórico, exportação, feedback estruturado ou fontes mais navegáveis.
- Operadores precisam rever/promover/rejeitar documentos sem usar API direta.
- Há necessidade de roles por organização ou multi-tenant.
- A experiência Dify impede mostrar evidência, avisos ou abstenção com clareza suficiente.
- O produto entra em beta paga ou pré-comercial.

## Próximas ações

- Usar Dify no próximo piloto acompanhado.
- Melhorar apenas o mínimo da apresentação Dify: fontes, avisos, `audit_id`, abstenção e feedback.
- Definir wireframes da UI própria antes de implementar frontend.
- Reavaliar esta decisão após a primeira beta com advogados.
