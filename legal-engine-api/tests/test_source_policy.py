from pathlib import Path

from app.source_policy import SourcePolicy, SourcePolicyStatus, domain_matches, normalize_url_domain


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def test_loads_source_policy_from_documented_yaml():
    policy = SourcePolicy.from_file(POLICY_PATH)

    assert policy.version == 1
    assert policy.name == "legal_ai_source_policy"
    assert policy.find_authority("diariodarepublica.pt") is not None
    assert policy.find_authority("eur-lex.europa.eu") is not None


def test_official_authority_may_ground_answer():
    policy = SourcePolicy.from_file(POLICY_PATH)

    result = policy.check_url("https://diariodarepublica.pt/dr/legislacao-consolidada/codigo-civil")

    assert result.status == SourcePolicyStatus.OFFICIAL_AUTHORITY
    assert result.domain == "diariodarepublica.pt"
    assert result.may_ground_answer is True
    assert result.authority is not None
    assert result.authority.source == "DRE"


def test_official_authority_matches_subdomain():
    policy = SourcePolicy.from_file(POLICY_PATH)

    result = policy.check_url("https://eur-lex.europa.eu/legal-content/PT/TXT/")

    assert result.status == SourcePolicyStatus.OFFICIAL_AUTHORITY
    assert result.authority is not None
    assert result.authority.source == "EURLEX"


def test_discovery_only_domain_cannot_ground_answer():
    policy = SourcePolicy.from_file(POLICY_PATH)

    result = policy.check_url("https://www.gov.pt/noticias/exemplo")

    assert result.status == SourcePolicyStatus.DISCOVERY_ONLY
    assert result.domain == "gov.pt"
    assert result.may_ground_answer is False
    assert result.authority is None


def test_blocked_domain_takes_precedence_over_unknown():
    policy = SourcePolicy.from_file(POLICY_PATH)

    result = policy.check_url("https://pt.wikipedia.org/wiki/Codigo_Civil")

    assert result.status == SourcePolicyStatus.BLOCKED
    assert result.domain == "pt.wikipedia.org"
    assert result.may_ground_answer is False


def test_unknown_domain_cannot_ground_answer():
    policy = SourcePolicy.from_file(POLICY_PATH)

    result = policy.check_url("https://example.com/legal")

    assert result.status == SourcePolicyStatus.UNKNOWN_DOMAIN
    assert result.domain == "example.com"
    assert result.may_ground_answer is False


def test_invalid_url_is_rejected():
    policy = SourcePolicy.from_file(POLICY_PATH)

    result = policy.check_url("not-a-url")

    assert result.status == SourcePolicyStatus.INVALID_URL
    assert result.domain is None
    assert result.may_ground_answer is False


def test_domain_helpers_normalize_and_match_subdomains():
    assert normalize_url_domain("https://www.dgsi.pt/jstj") == "dgsi.pt"
    assert domain_matches("sub.dgsi.pt", "dgsi.pt") is True
    assert domain_matches("maliciousdgsi.pt", "dgsi.pt") is False
