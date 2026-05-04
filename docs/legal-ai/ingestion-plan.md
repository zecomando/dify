# Plano de ingestão jurídica

## Objetivo

Criar um pipeline fiável para transformar fontes oficiais em documentos, chunks e evidências utilizáveis no chat jurídico.

## Estado local validado

O `legal-engine-api` já implementa a ingestão local determinística necessária para demo técnica:

- `POST /ingestion/source` aceita URL oficial, texto bruto opcional, metadados jurídicos e flag de promoção.
- `POST /ingestion/crawl-url` faz fetch HTTP inicial para DRE/EUR-Lex, normaliza HTML/texto, extrai metadados básicos e cria documento/job.
- `legal-seed` e `POST /admin/corpus/seed` criam um corpus inicial oficial e idempotente por `source_url`.
- O texto bruto é persistido quando fornecido.
- O SHA-256 é calculado a partir da URL e do texto bruto.
- O chunking por artigo cria chunks rastreáveis ao documento.
- `legal_metadata` é persistido e propagado para retrieval, evidence e respostas.
- A source policy bloqueia domínios não oficiais e impede `chat_ready` quando faltam requisitos jurídicos.
- `POST /admin/reindex` reprocessa documentos a partir do bruto persistido.
- `GET /admin/ingestion/jobs` e `GET /admin/ingestion/jobs/{job_id}` permitem diagnóstico operacional.

Ainda não implementado:

- Fetch remoto robusto para todas as fontes oficiais.
- Parsing robusto de PDF/XML e HTML complexo.
- Extração automática completa de metadados jurídicos.
- Hardening de embeddings externos e vector store de produção.
- Arquivo automático de versões anteriores.
- Fila de aprovação humana para jurisprudência e fontes sensíveis.

## Princípios

- Guardar sempre o bruto antes de processar.
- Gerar hash SHA-256 de cada documento.
- Separar discovery de fundamentação.
- Promover para `chat_ready` apenas após validação.
- Preservar metadados jurídicos e temporais.
- Manter versões antigas para auditoria e perguntas históricas.

## Pipeline comum

### Pipeline local atual

```text
seed/manual/crawl source
  ↓
Validação de domínio e authority rule
  ↓
Fetch/parsing inicial quando `/ingestion/crawl-url` suporta a autoridade
  ↓
Guardar documento, texto bruto, SHA-256 e metadados declarados ou extraídos
  ↓
Chunking por artigo
  ↓
Validação de requisitos mínimos da source policy
  ↓
Promoção para chat_ready ou pending_review
  ↓
Retrieval lexical/evidence/auditoria
```

### Pipeline alvo beta/produção

```text
URL/API/seed
  ↓
Validação de domínio
  ↓
Fetch ou Firecrawl
  ↓
Guardar bruto em storage
  ↓
Docling/LlamaParse quando necessário
  ↓
Normalização
  ↓
Extração de metadados
  ↓
Chunking estrutural
  ↓
Validação de qualidade
  ↓
Embeddings
  ↓
Indexação vetorial
  ↓
Promoção para chat_ready ou pending_review
```

## Ordem de implementação restante

1. **Hardening do fetch remoto DRE/EUR-Lex**
   - O adapter HTTP inicial já existe com timeout, limite de bytes e user-agent identificável.
   - Falta adicionar retries/backoff configurável e métricas operacionais.
   - Manter rejeição ou `pending_review` quando a extração for incompleta.

2. **Parser robusto por fonte**
   - DRE: HTML consolidado simples já entra como texto/artigos; falta parsing estrutural completo.
   - EUR-Lex: CELEX e tipo de ato básico já são extraídos; faltam anexos, ELI e versões consolidadas robustas.
   - HUDOC/Curia/DGSI: metadados mínimos e corpo decisório apenas com aprovação humana.

3. **Hardening de embeddings e vector store**
   - `EmbeddingProvider` local determinístico e índice SQLite já existem.
   - Falta criar adapters externos de embeddings e vector store.
   - Guardar identificadores externos por chunk quando Pinecone/Qdrant estiver ativo.
   - Manter retrieval lexical como fallback determinístico e para testes.

4. **Versionamento**
   - Quando o hash mudar, criar nova versão documental.
   - Marcar versão anterior como `archived`.
   - Preservar cadeia de alteração para perguntas “à data de”.

5. **Revisão humana**
   - Jurisprudência começa sempre em `pending_review`.
   - Promoção exige metadados mínimos, fonte oficial e aprovação.
   - Rejeição deve guardar motivo auditável.

## Estados

- `raw`: bruto guardado, ainda sem parsing.
- `fetched`: URL oficial recolhida com sucesso.
- `parsed`: texto estruturado extraído.
- `normalized`: metadados e estrutura normalizados.
- `chunked`: chunks criados e persistidos.
- `embedded`: embeddings criados e indexados.
- `validated`: requisitos de qualidade cumpridos.
- `pending_review`: requer revisão humana ou metadados adicionais.
- `chat_ready`: elegível para fundamentar respostas.
- `archived`: versão antiga preservada para auditoria/perguntas históricas.
- `rejected`: fonte rejeitada, com motivo guardado no job.

No MVP local, os estados persistidos são simplificados para `pending_review`, `chat_ready`, `archived` e `rejected`, com jobs de ingestão/reindexação a indicar `pending`, `completed` ou `rejected`.

## DRE

### Objetivo — DRE

Ingerir legislação portuguesa oficial, incluindo versões consolidadas e atos originais quando disponíveis.

### Metadados — DRE

- Título.
- Diploma.
- Número.
- Data.
- URL oficial.
- Data de versão.
- Estado de vigência.
- Indicação de consolidação.
- Aviso de ausência de valor legal autónomo.

### Chunking — DRE

```text
Diploma
  > Parte
  > Livro
  > Título
  > Capítulo
  > Secção
  > Artigo
  > Número
  > Alínea
```

### Regras — DRE

- Marcar `is_consolidated=true` quando aplicável.
- Incluir aviso legal obrigatório.
- Tentar guardar referência aos atos modificativos.
- Marcar versões anteriores como `archived`, não apagar.

## EUR-Lex

### Objetivo — EUR-Lex

Ingerir tratados, regulamentos, diretivas, decisões e textos consolidados da União Europeia.

### Metadados — EUR-Lex

- CELEX.
- ELI, se disponível.
- Tipo de ato.
- Data de publicação.
- Data de efeito.
- Data da versão consolidada.
- Lista de atos modificativos, se disponível.

### Chunking — EUR-Lex

```text
Ato
  > Considerandos
  > Artigos
  > Anexos
```

### Regras — EUR-Lex

- Marcar textos consolidados com aviso de ausência de valor jurídico autónomo.
- Preservar CELEX.
- Preservar ELI.
- Permitir perguntas “à data de” usando versões arquivadas.

## DGSI

### Objetivo — DGSI

Ingerir jurisprudência nacional selecionada.

### Metadados obrigatórios — DGSI

- Tribunal.
- Data de decisão.
- Processo.
- Relator, se disponível.
- Descritores.
- Sumário.
- URL oficial.

### Chunking — DGSI

- Sumário.
- Fundamentação.
- Decisão.
- Tese jurídica.

### Regras — DGSI

- Não promover decisão sem tribunal, data e processo.
- Priorizar tribunais superiores.
- Exigir aprovação humana no MVP.

## Tribunal Constitucional

### Objetivo — Tribunal Constitucional

Ingerir acórdãos relevantes para constitucionalidade e direitos fundamentais.

### Regras — Tribunal Constitucional

- Preservar número de acórdão.
- Preservar processo.
- Preservar data.
- Preservar tipo de fiscalização, quando possível.

## Curia / InfoCuria

### Objetivo — Curia / InfoCuria

Ingerir jurisprudência do TJUE.

### Metadados — Curia / InfoCuria

- Tribunal.
- Data.
- Número do processo.
- ECLI.
- Partes.
- Matéria.
- URL oficial.

### Regras — Curia / InfoCuria

- Preservar número de processo.
- Preservar ECLI quando disponível.
- Separar conclusões do Advogado-Geral de acórdãos.

## HUDOC / TEDH

### Objetivo — HUDOC / TEDH

Ingerir jurisprudência CEDH/TEDH relevante.

### Metadados — HUDOC / TEDH

- Application number.
- Case title.
- Court.
- Decision date.
- Importance level.
- Articles ECHR.
- URL oficial.

## BASE / IMPIC

### Objetivo — BASE / IMPIC

Ingerir dados de contratação pública nacional.

### Metadados — BASE / IMPIC

- Entidade adjudicante.
- Adjudicatário.
- Procedimento.
- Preço contratual.
- CPV.
- Datas.
- URL oficial.

### Regras — BASE / IMPIC

- Confirmar termos de acesso e autorização para extração de grandes volumes.
- Separar dados de contratação pública de conclusões jurídicas.

## TED

### Objetivo — TED

Ingerir notices europeus de contratação pública.

### Metadados — TED

- Notice ID.
- Buyer.
- Procedure type.
- CPV.
- Publication date.
- Country.
- Value.
- URL oficial.

## Validação de qualidade

Um documento só pode ser promovido para `chat_ready` se:

- Domínio permitido.
- Texto extraído com sucesso.
- Metadados mínimos presentes.
- Chunks não vazios.
- Hash guardado.
- Source policy cumprida.

Para beta/produção, acrescentar:

- Embeddings externos criados.
- Chunks indexados no vector store externo.
- `vector_id` externo persistido por chunk.
- Avisos de consolidação/vigência presentes quando aplicável.
- Jurisprudência aprovada por humano quando a source policy ou critérios editoriais exigirem.

## Critérios por fonte antes de `chat_ready`

- **DRE:** artigo ou identificador legal preservado; vigência/consolidação marcada; aviso de texto consolidado quando aplicável.
- **EUR-Lex:** CELEX preservado; tipo de ato correto; versão consolidada marcada quando aplicável.
- **DGSI:** tribunal, data e processo presentes; decisão selecionada por critério editorial; aprovação humana.
- **Tribunal Constitucional:** número de acórdão/processo e data presentes.
- **Curia/TJUE:** tribunal, data, número de processo e ECLI quando disponível.
- **HUDOC/TEDH:** application number, court e decision date presentes.
- **BASE/TED:** separar dado de contratação pública de conclusão jurídica; CPV/notice ID quando disponível.

## Reprocessamento

Reprocessar quando:

- Hash de fonte muda.
- Parser muda.
- Chunker muda.
- Modelo de embeddings muda.
- Política de fonte muda.

O reprocessamento deve sempre:

- Criar job consultável em `/admin/ingestion/jobs`.
- Manter o documento anterior auditável até a nova versão estar validada.
- Recalcular chunks e embeddings.
- Executar smoke retrieval/evidence em amostra canónica.
- Alertar operador quando documentos forem movidos para `pending_review` ou `rejected`.
