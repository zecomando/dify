from pathlib import Path

from app.feedback_triage import list_feedback_triage, main
from app.pipeline import answer_chat
from app.repository import AnswerFeedbackRecord, LegalRepository, utc_now_iso
from app.schemas import ChatAnswerRequest
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def _seed_feedback(repository: LegalRepository) -> str:
    response = answer_chat(
        ChatAnswerRequest(question="responsabilidade civil", session_id="session-triage", user_id="user-triage"),
        _source_policy(),
        repository,
    )
    repository.create_answer_feedback(
        AnswerFeedbackRecord(
            id="feedback-negative",
            audit_id=response.audit_id,
            rating="negative",
            category="legal_error",
            comment="A resposta não tratou o regime aplicável.",
            user_id="user-triage",
            session_id="session-triage",
            created_at=utc_now_iso(),
        )
    )
    repository.create_answer_feedback(
        AnswerFeedbackRecord(
            id="feedback-neutral",
            audit_id=response.audit_id,
            rating="neutral",
            category="too_vague",
            comment="Pode melhorar.",
            user_id="user-triage",
            session_id="session-triage",
            created_at=utc_now_iso(),
        )
    )
    return response.audit_id


def test_list_feedback_triage_returns_negative_feedback_with_audit_context(tmp_path: Path):
    repository = LegalRepository(tmp_path / "feedback-triage.sqlite3")
    audit_id = _seed_feedback(repository)

    result = list_feedback_triage(repository, category="legal_error")

    assert result.total == 1
    assert len(result.items) == 1
    item = result.items[0]
    assert item.feedback.id == "feedback-negative"
    assert item.audit.id == audit_id
    assert item.audit.user_query == "responsabilidade civil"
    assert item.evidence_count >= 0


def test_feedback_triage_cli_prints_json_result(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "feedback-triage.sqlite3")
    _seed_feedback(repository)
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-feedback-triage",
            "--database-path",
            str(tmp_path / "feedback-triage.sqlite3"),
            "--category",
            "legal_error",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"total": 1' in captured.out
    assert '"feedback"' in captured.out
    assert '"audit_id":' in captured.out
    assert '"user_query": "responsabilidade civil"' in captured.out
    assert '"final_answer":' in captured.out


def test_feedback_triage_cli_prints_human_result(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "feedback-triage.sqlite3")
    _seed_feedback(repository)
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-feedback-triage",
            "--database-path",
            str(tmp_path / "feedback-triage.sqlite3"),
            "--category",
            "legal_error",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "negative feedback triage: total=1, shown=1" in captured.out
    assert "feedback-negative" in captured.out
    assert "legal_error" in captured.out
    assert "responsabilidade civil" in captured.out
