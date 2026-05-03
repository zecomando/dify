# Plano de ingestão jurídica

## Objetivo

Criar um pipeline fiável para transformar fontes oficiais em documentos, chunks e evidências utilizáveis no chat jurídico.

## Princípios

- Guardar sempre o bruto antes de processar.
- Gerar hash SHA-256 de cada documento.
- Separar discovery de fundamentação.
- Promover para `chat_ready` apenas após validação.
- Preservar metadados jurídicos e temporais.
- Manter versões antigas para auditoria e perguntas históricas.

## Pipeline comum

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

## Estados

- `raw`
- `fetched`
- `parsed`
- `normalized`
- `chunked`
- `embedded`
- `validated`
- `chat_ready`
- `archived`
- `rejected`

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
- Embeddings criados.
- Source policy cumprida.

## Reprocessamento

Reprocessar quando:

- Hash de fonte muda.
- Parser muda.
- Chunker muda.
- Modelo de embeddings muda.
- Política de fonte muda.
