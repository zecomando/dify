from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion import ingest_source
from app.repository import LegalRepository
from app.schemas import IngestionJobStatus, IngestionSourceRequest
from app.source_policy import SourcePolicy


@dataclass(frozen=True, slots=True)
class InitialCorpusSeed:
    source_url: str
    area: str
    document_type: str
    raw_text: str
    jurisdiction: str = "portugal"
    legal_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InitialCorpusSeedResult:
    total_seeds: int
    created_documents: int
    already_present_documents: int
    completed_jobs: int
    rejected_jobs: int
    chat_ready_documents: int
    pending_review_documents: int
    document_ids: tuple[str, ...]
    rejected_source_urls: tuple[str, ...]


def seed_initial_corpus(repository: LegalRepository, source_policy: SourcePolicy) -> InitialCorpusSeedResult:
    created_documents = 0
    already_present_documents = 0
    completed_jobs = 0
    rejected_jobs = 0
    chat_ready_documents = 0
    pending_review_documents = 0
    document_ids: list[str] = []
    rejected_source_urls: list[str] = []

    for seed in initial_corpus_seeds():
        existing_document = repository.get_document_by_source_url(seed.source_url)
        if existing_document is not None:
            already_present_documents += 1
            document_ids.append(existing_document.id)
            if existing_document.status == "chat_ready":
                chat_ready_documents += 1
            elif existing_document.status == "pending_review":
                pending_review_documents += 1
            continue

        response = ingest_source(
            IngestionSourceRequest(
                source_url=seed.source_url,
                raw_text=seed.raw_text,
                jurisdiction=seed.jurisdiction,
                document_type=seed.document_type,
                area=[seed.area],
                legal_metadata=seed.legal_metadata,
                promote_if_valid=True,
            ),
            source_policy,
            repository,
        )
        job = repository.get_job(response.job_id)
        if response.status == IngestionJobStatus.REJECTED or job is None or job.document_id is None:
            rejected_jobs += 1
            rejected_source_urls.append(seed.source_url)
            continue

        completed_jobs += 1
        created_documents += 1
        document_ids.append(job.document_id)
        document = repository.get_document(job.document_id)
        if document is not None and document.status == "chat_ready":
            chat_ready_documents += 1
        elif document is not None and document.status == "pending_review":
            pending_review_documents += 1

    return InitialCorpusSeedResult(
        total_seeds=len(initial_corpus_seeds()),
        created_documents=created_documents,
        already_present_documents=already_present_documents,
        completed_jobs=completed_jobs,
        rejected_jobs=rejected_jobs,
        chat_ready_documents=chat_ready_documents,
        pending_review_documents=pending_review_documents,
        document_ids=tuple(document_ids),
        rejected_source_urls=tuple(rejected_source_urls),
    )


def initial_corpus_seeds() -> tuple[InitialCorpusSeed, ...]:
    return (
        InitialCorpusSeed(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-dos-contratos-publicos",
            area="contratacao_publica",
            document_type="legislation",
            raw_text=(
                "Artigo 1.º\n"
                "O Código dos Contratos Públicos regula a formação e execução de contratos públicos.\n\n"
                "Artigo 2.º\n"
                "A exclusão de proposta por preço anormalmente baixo exige análise e pedido de esclarecimentos."
            ),
        ),
        InitialCorpusSeed(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-do-procedimento-administrativo",
            area="administrativo",
            document_type="legislation",
            raw_text=(
                "Artigo 1.º\nA audiência prévia é uma garantia procedimental antes da decisão administrativa final."
            ),
        ),
        InitialCorpusSeed(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            area="civil",
            document_type="legislation",
            raw_text=(
                "Artigo 1.º\n"
                "A responsabilidade civil extracontratual depende de facto, ilicitude, culpa, dano e nexo causal.\n\n"
                "Artigo 2.º\n"
                "A obrigação de indemnizar exige prova dos pressupostos legais aplicáveis."
            ),
        ),
        InitialCorpusSeed(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-do-trabalho",
            area="laboral",
            document_type="legislation",
            raw_text=(
                "Artigo 1.º\n"
                "O despedimento por justa causa exige comportamento culposo que torne impossível a relação laboral."
            ),
        ),
        InitialCorpusSeed(
            source_url="https://dre.pt/dre/legislacao-consolidada/lei-geral-tributaria",
            area="fiscal",
            document_type="legislation",
            raw_text=(
                "Artigo 1.º\n"
                "O prazo de caducidade do direito à liquidação tributária deve ser confirmado na lei vigente."
            ),
        ),
        InitialCorpusSeed(
            source_url="https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:32016R0679",
            area="proteccao_dados",
            document_type="legislation",
            raw_text=(
                "Artigo 6.º\nO RGPD, CELEX:32016R0679, prevê bases de licitude para o tratamento de dados pessoais."
            ),
            jurisdiction="europa",
            legal_metadata={"celex": "32016R0679"},
        ),
        InitialCorpusSeed(
            source_url="https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:12012M",
            area="uniao_europeia",
            document_type="treaty",
            raw_text=(
                "Artigo 1.º\nO Tratado da União Europeia, CELEX:12012M, integra a ordem jurídica da União Europeia."
            ),
            jurisdiction="europa",
            legal_metadata={"celex": "12012M"},
        ),
        InitialCorpusSeed(
            source_url="https://www.dgsi.pt/jstj.nsf/-/demo-123-20.0T8LSB",
            area="civil",
            document_type="case_law",
            raw_text=(
                "Processo 123/20.0T8LSB\n"
                "O Supremo Tribunal de Justiça apreciou pressupostos de responsabilidade civil e nexo causal."
            ),
            legal_metadata={
                "court": "Supremo Tribunal de Justiça",
                "decision_date": "2024-01-01",
                "process_number": "123/20.0T8LSB",
            },
        ),
        InitialCorpusSeed(
            source_url="https://www.tribunalconstitucional.pt/tc/acordaos/20240001.html",
            area="constitucional",
            document_type="case_law",
            raw_text=(
                "Processo 1/2024\nO Tribunal Constitucional apreciou a conformidade constitucional de norma legal."
            ),
            legal_metadata={
                "court": "Tribunal Constitucional",
                "decision_date": "2024-01-15",
                "process_number": "1/2024",
            },
        ),
        InitialCorpusSeed(
            source_url="https://curia.europa.eu/juris/document/document.jsf?docid=228677",
            area="proteccao_dados",
            document_type="case_law",
            raw_text=(
                "Processo C-311/18\nO Tribunal de Justiça da União Europeia decidiu o caso com ECLI:EU:C:2020:559."
            ),
            jurisdiction="europa",
            legal_metadata={
                "court": "Tribunal de Justiça da União Europeia",
                "decision_date": "2020-07-16",
                "case_number": "C-311/18",
            },
        ),
        InitialCorpusSeed(
            source_url="https://hudoc.echr.coe.int/eng?i=001-article-6-demo",
            area="cedh",
            document_type="case_law",
            raw_text=(
                "Artigo 6.º\n"
                "A Convenção Europeia dos Direitos Humanos protege o direito a um processo equitativo, incluindo garantias de julgamento justo."
            ),
            jurisdiction="europa",
            legal_metadata={
                "court": "Tribunal Europeu dos Direitos Humanos",
                "decision_date": "2024-01-01",
                "application_number": "00001/24",
            },
        ),
        InitialCorpusSeed(
            source_url="https://ted.europa.eu/pt/notice/example",
            area="contratacao_publica",
            document_type="procurement_notice",
            raw_text=(
                "Artigo 1.º\nO TED publica anúncios de contratação pública europeus e informação sobre procedimentos."
            ),
            jurisdiction="europa",
        ),
        InitialCorpusSeed(
            source_url="https://www.base.gov.pt/Base4/pt/detalhe/?type=contratos&id=demo",
            area="contratacao_publica",
            document_type="public_contract",
            raw_text=(
                "Artigo 1.º\nO portal BASE contém dados de contratos públicos, adjudicação e entidade adjudicante."
            ),
        ),
    )
