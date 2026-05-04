from pathlib import Path

from app.demo import main, run_demo


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def test_run_demo_seeds_corpus_and_passes_default_cases(tmp_path: Path):
    result = run_demo(
        database_path=tmp_path / "demo.sqlite3",
        source_policy_path=POLICY_PATH,
    )

    assert result.passed is True
    assert result.seed_created_documents > 0
    assert result.seed_chat_ready_documents == result.seed_created_documents
    assert result.seed_rejected_jobs == 0
    assert {case.id for case in result.cases} == {"civil-liability", "rgpd-lawfulness", "insufficient-source"}
    assert all(case.audit_id for case in result.cases)
    assert any(case.verdict == "abstain" for case in result.cases)


def test_run_demo_is_idempotent_on_existing_seeded_database(tmp_path: Path):
    database_path = tmp_path / "demo.sqlite3"

    first_result = run_demo(database_path=database_path, source_policy_path=POLICY_PATH)
    second_result = run_demo(database_path=database_path, source_policy_path=POLICY_PATH)

    assert first_result.passed is True
    assert second_result.passed is True
    assert second_result.seed_created_documents == 0
    assert second_result.seed_already_present_documents == first_result.seed_created_documents


def test_run_demo_custom_questions_are_expected_to_pass(tmp_path: Path):
    result = run_demo(
        database_path=tmp_path / "demo.sqlite3",
        source_policy_path=POLICY_PATH,
        questions=("Quais são os pressupostos da responsabilidade civil extracontratual?",),
    )

    assert result.passed is True
    assert len(result.cases) == 1
    assert result.cases[0].id == "custom-1"
    assert result.cases[0].verdict == "pass"


def test_demo_cli_prints_json_result(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-demo",
            "--database-path",
            str(tmp_path / "demo.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert '"civil-liability"' in captured.out
