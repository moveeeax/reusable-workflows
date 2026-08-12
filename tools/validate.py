#!/usr/bin/env python3
"""Validate the reusable-workflow library against the project's acceptance rules.

Checks, for every YAML file under ``.github/workflows`` (except this repo's own
``ci.yml`` orchestrator) and every example caller under ``examples/``:

* reusable workflows expose ``on.workflow_call``;
* every ``workflow_call`` input carries a human-readable ``description``;
* every third-party ``uses:`` reference is pinned to a full 40-character commit
  SHA (local ``./`` actions and GitHub-owned ``docker://`` refs are exempt);
* every workflow declares an explicit ``permissions`` block (least privilege);
* example callers reference a workflow that actually ships in this repo.

Run it directly for a report::

    python3 tools/validate.py

Exit code is non-zero when any rule fails, which is what ``ci.yml`` relies on.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# A pinned action ref looks like ``owner/repo@<40-hex>`` or
# ``owner/repo/path@<40-hex>``.
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_SLUG = "moveeeax/reusable-workflows"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _on_block(doc: dict[str, Any]) -> Any:
    """Return the ``on:`` mapping.

    PyYAML parses the bare key ``on`` as the boolean ``True`` (a YAML 1.1
    quirk), so accept either spelling.
    """
    if "on" in doc:
        return doc["on"]
    return doc.get(True)


def _iter_uses(node: Any):
    """Yield every ``uses:`` string value found anywhere in the document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses" and isinstance(value, str):
                yield value
            else:
                yield from _iter_uses(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_uses(item)


def _is_third_party(uses: str) -> bool:
    if uses.startswith("./") or uses.startswith("docker://"):
        return False
    # Same-repo reusable workflow references are pinned by tag by design.
    if uses.startswith(REPO_SLUG):
        return False
    return "@" in uses


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, path: Path, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_pinning(path: Path, doc: dict[str, Any], report: Report) -> None:
    for uses in _iter_uses(doc):
        if not _is_third_party(uses):
            continue
        ref = uses.split("@", 1)[1]
        if not SHA_RE.match(ref):
            report.fail(path, f"action '{uses}' is not pinned to a 40-char commit SHA")


def _check_permissions(path: Path, doc: dict[str, Any], report: Report) -> None:
    if "permissions" in doc:
        return
    jobs = doc.get("jobs") or {}
    if jobs and all("permissions" in job for job in jobs.values()):
        return
    report.fail(path, "no explicit 'permissions' block (least privilege required)")


def _check_reusable(path: Path, doc: dict[str, Any], report: Report) -> None:
    on = _on_block(doc)
    if not isinstance(on, dict) or "workflow_call" not in on:
        report.fail(path, "reusable workflow must declare 'on.workflow_call'")
        return
    call = on["workflow_call"] or {}
    inputs = (call or {}).get("inputs") or {}
    for name, spec in inputs.items():
        spec = spec or {}
        if not spec.get("description"):
            report.fail(path, f"workflow_call input '{name}' is missing a description")


def validate(root: Path | None = None) -> Report:
    root = root or _repo_root()
    report = Report()

    wf_dir = root / ".github" / "workflows"
    reusable = sorted(p for p in wf_dir.glob("*.yml") if p.name != "ci.yml")
    if not reusable:
        report.fail(wf_dir, "no reusable workflows found")

    shipped = {p.name for p in reusable}

    for path in reusable:
        report.checked += 1
        doc = _load_yaml(path)
        _check_reusable(path, doc, report)
        _check_pinning(path, doc, report)
        _check_permissions(path, doc, report)

    # ci.yml is the repo's own orchestrator: it still must pin actions.
    ci = wf_dir / "ci.yml"
    if ci.exists():
        report.checked += 1
        _check_pinning(ci, _load_yaml(ci), report)

    examples = sorted((root / "examples").glob("*.yml"))
    if not examples:
        report.fail(root / "examples", "no example callers found")
    for path in examples:
        report.checked += 1
        doc = _load_yaml(path)
        _check_pinning(path, doc, report)
        refs = [u for u in _iter_uses(doc) if u.startswith(REPO_SLUG)]
        if not refs:
            report.fail(path, "example does not reference a reusable-workflows workflow")
        for ref in refs:
            wf_name = ref.split("@", 1)[0].split("/")[-1]
            if wf_name not in shipped:
                report.fail(path, f"references unknown workflow '{wf_name}'")

    return report


def main(argv: list[str]) -> int:
    report = validate()
    if report.ok:
        print(f"OK: {report.checked} workflow file(s) validated, 0 errors.")
        return 0
    print(f"FAIL: {len(report.errors)} problem(s) across {report.checked} file(s):")
    for err in report.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
