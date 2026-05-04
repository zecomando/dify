from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class N8nWorkflowValidationResult:
    path: str
    passed: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class N8nWorkflowValidationSummary:
    passed: bool
    workflows: tuple[N8nWorkflowValidationResult, ...]


def get_default_n8n_workflows_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "n8n"


def validate_n8n_workflows(workflows_dir: Path) -> N8nWorkflowValidationSummary:
    workflow_paths = tuple(sorted(workflows_dir.glob("*.json")))
    if not workflow_paths:
        return N8nWorkflowValidationSummary(
            passed=False,
            workflows=(
                N8nWorkflowValidationResult(
                    path=str(workflows_dir),
                    passed=False,
                    errors=("No n8n workflow JSON exports were found.",),
                ),
            ),
        )
    results = tuple(_validate_workflow(path) for path in workflow_paths)
    return N8nWorkflowValidationSummary(passed=all(result.passed for result in results), workflows=results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Legal AI n8n workflow exports without executing n8n.")
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=get_default_n8n_workflows_dir(),
        help="Path to docs/legal-ai/n8n workflow exports.",
    )
    parser.add_argument("--json", action="store_true", help="Print validation result as JSON.")
    args = parser.parse_args()

    summary = validate_n8n_workflows(args.workflows_dir)
    if args.json:
        print(json.dumps(_summary_dict(summary), ensure_ascii=False, indent=2))
    else:
        _print_summary(summary)
    return 0 if summary.passed else 1


def _validate_workflow(path: Path) -> N8nWorkflowValidationResult:
    errors: list[str] = []
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return N8nWorkflowValidationResult(path=str(path), passed=False, errors=(f"Invalid JSON: {exc}",))
    if not isinstance(workflow, dict):
        return N8nWorkflowValidationResult(
            path=str(path), passed=False, errors=("Workflow export must be a JSON object.",)
        )

    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if not isinstance(workflow.get("name"), str) or not workflow["name"].strip():
        errors.append("Workflow name is missing.")
    if not isinstance(workflow.get("versionId"), str) or not workflow["versionId"].strip():
        errors.append("Workflow versionId is missing.")
    if not isinstance(nodes, list) or not nodes:
        errors.append("Workflow nodes must be a non-empty array.")
        nodes = []
    if not isinstance(connections, dict):
        errors.append("Workflow connections must be an object.")
        connections = {}

    node_names = _node_names(nodes)
    errors.extend(_validate_nodes(nodes))
    errors.extend(_validate_connections(connections, node_names))
    errors.extend(_validate_no_literal_secrets(workflow))
    return N8nWorkflowValidationResult(path=str(path), passed=not errors, errors=tuple(errors))


def _node_names(nodes: Iterable[object]) -> set[str]:
    names: set[str] = set()
    for node in nodes:
        if isinstance(node, dict) and isinstance(node.get("name"), str):
            names.add(node["name"])
    return names


def _validate_nodes(nodes: Iterable[object]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("Every workflow node must be an object.")
            continue
        node_id = node.get("id")
        node_name = node.get("name")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append("Node id is missing.")
        elif node_id in seen_ids:
            errors.append(f"Duplicate node id: {node_id}.")
        else:
            seen_ids.add(node_id)
        if not isinstance(node_name, str) or not node_name.strip():
            errors.append(f"Node {node_id or '<unknown>'} name is missing.")
        elif node_name in seen_names:
            errors.append(f"Duplicate node name: {node_name}.")
        else:
            seen_names.add(node_name)
        if not isinstance(node_type, str) or not node_type.startswith("n8n-nodes-base."):
            errors.append(f"Node {node_name or node_id or '<unknown>'} has an invalid n8n type.")
        parameters = node.get("parameters")
        if not isinstance(parameters, dict):
            errors.append(f"Node {node_name or node_id or '<unknown>'} parameters must be an object.")
            continue
        if node_type == "n8n-nodes-base.httpRequest":
            errors.extend(_validate_http_node(node_name or node_id or "<unknown>", parameters))
        if node_type == "n8n-nodes-base.code":
            errors.extend(_validate_code_node(node_name or node_id or "<unknown>", parameters))
    return errors


def _validate_http_node(node_name: str, parameters: dict[str, object]) -> list[str]:
    errors: list[str] = []
    url = parameters.get("url")
    if not isinstance(url, str) or "$env.LEGAL_ENGINE_BASE_URL" not in url:
        errors.append(f"HTTP node {node_name} must build url from $env.LEGAL_ENGINE_BASE_URL.")
    if isinstance(url, str) and _contains_literal_url(url):
        errors.append(f"HTTP node {node_name} must not contain a hardcoded absolute URL.")
    if isinstance(url, str) and "/admin/" in url:
        headers = _header_parameters(parameters)
        token_values = [value for name, value in headers if name.lower() == "x-admin-token"]
        if not token_values:
            errors.append(f"Admin HTTP node {node_name} must send X-Admin-Token.")
        if any("$env.LEGAL_ENGINE_ADMIN_TOKEN" not in value for value in token_values):
            errors.append(f"Admin HTTP node {node_name} must read X-Admin-Token from $env.LEGAL_ENGINE_ADMIN_TOKEN.")
    return errors


def _validate_code_node(node_name: str, parameters: dict[str, object]) -> list[str]:
    js_code = parameters.get("jsCode")
    if not isinstance(js_code, str) or "throw new Error" not in js_code:
        return [f"Code node {node_name} must fail explicitly with throw new Error."]
    return []


def _validate_connections(connections: dict[object, object], node_names: set[str]) -> list[str]:
    errors: list[str] = []
    for source_name, source_connections in connections.items():
        if not isinstance(source_name, str) or source_name not in node_names:
            errors.append(f"Connection source node does not exist: {source_name}.")
        for target in _connection_targets(source_connections):
            if target not in node_names:
                errors.append(f"Connection target node does not exist: {target}.")
    return errors


def _validate_no_literal_secrets(value: object) -> list[str]:
    errors: list[str] = []
    for text in _walk_strings(value):
        if "$env." in text:
            continue
        if _secret_like_pattern().search(text):
            errors.append("Workflow contains a literal value that looks like a secret.")
            break
    return errors


def _header_parameters(parameters: dict[str, object]) -> tuple[tuple[str, str], ...]:
    header_parameters = parameters.get("headerParameters")
    if not isinstance(header_parameters, dict):
        return ()
    entries = header_parameters.get("parameters")
    if not isinstance(entries, list):
        return ()
    headers: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if isinstance(name, str) and isinstance(value, str):
            headers.append((name, value))
    return tuple(headers)


def _connection_targets(source_connections: object) -> tuple[str, ...]:
    targets: list[str] = []
    if not isinstance(source_connections, dict):
        return ()
    for outputs in source_connections.values():
        if not isinstance(outputs, list):
            continue
        for output_group in outputs:
            if not isinstance(output_group, list):
                continue
            for edge in output_group:
                if isinstance(edge, dict) and isinstance(edge.get("node"), str):
                    targets.append(edge["node"])
    return tuple(targets)


def _walk_strings(value: object) -> tuple[str, ...]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            strings.extend(_walk_strings(key))
            strings.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_walk_strings(item))
    return tuple(strings)


def _contains_literal_url(value: str) -> bool:
    return bool(re.search(r"https?://", value, flags=re.IGNORECASE))


def _secret_like_pattern() -> re.Pattern[str]:
    return re.compile(
        r"(?:sk-[A-Za-z0-9_-]{12,}|pk_[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,}|password\s*[:=]|api[_-]?key\s*[:=])",
        flags=re.IGNORECASE,
    )


def _summary_dict(summary: N8nWorkflowValidationSummary) -> dict[str, object]:
    return {
        "passed": summary.passed,
        "workflows": [
            {"path": result.path, "passed": result.passed, "errors": list(result.errors)}
            for result in summary.workflows
        ],
    }


def _print_summary(summary: N8nWorkflowValidationSummary) -> None:
    status = "PASS" if summary.passed else "FAIL"
    print(f"{status} n8n workflows: total={len(summary.workflows)}")
    for result in summary.workflows:
        workflow_status = "PASS" if result.passed else "FAIL"
        print(f"{workflow_status} {result.path}")
        for error in result.errors:
            print(f"  - {error}")


if __name__ == "__main__":
    raise SystemExit(main())
