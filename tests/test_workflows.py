"""Unit tests for the reusable-workflow library.

These map one-to-one onto the acceptance criteria in the project spec:

* each workflow is callable via ``workflow_call`` with documented inputs;
* all third-party actions are pinned by commit SHA;
* an example consumer workflow is provided for each reusable workflow.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import validate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WF_DIR = ROOT / ".github" / "workflows"
REUSABLE = sorted(p for p in WF_DIR.glob("*.yml") if p.name != "ci.yml")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_validator_passes_on_the_repo():
    report = validate.validate(ROOT)
    assert report.ok, "\n".join(report.errors)
    assert report.checked >= len(REUSABLE)


def test_there_are_reusable_workflows():
    names = {p.name for p in REUSABLE}
    # The MVP scope: lint/test starters + container build + sbom + release.
    for expected in ("go.yml", "python.yml", "terraform.yml", "docker.yml",
                     "sbom.yml", "release.yml"):
        assert expected in names, f"missing reusable workflow {expected}"


@pytest.mark.parametrize("path", REUSABLE, ids=lambda p: p.name)
def test_declares_workflow_call(path: Path):
    on = validate._on_block(_load(path))
    assert isinstance(on, dict) and "workflow_call" in on


@pytest.mark.parametrize("path", REUSABLE, ids=lambda p: p.name)
def test_inputs_are_documented(path: Path):
    call = validate._on_block(_load(path))["workflow_call"] or {}
    for name, spec in (call.get("inputs") or {}).items():
        assert (spec or {}).get("description"), f"{path.name}:{name} lacks a description"


@pytest.mark.parametrize("path", REUSABLE, ids=lambda p: p.name)
def test_reusable_workflow_has_permissions(path: Path):
    doc = _load(path)
    jobs = doc.get("jobs") or {}
    has_top = "permissions" in doc
    has_job = bool(jobs) and all("permissions" in j for j in jobs.values())
    assert has_top or has_job, f"{path.name} has no explicit permissions block"


def test_all_third_party_actions_pinned_by_sha():
    offenders = []
    for path in list(WF_DIR.glob("*.yml")) + list((ROOT / "examples").glob("*.yml")):
        for uses in validate._iter_uses(_load(path)):
            if validate._is_third_party(uses):
                ref = uses.split("@", 1)[1]
                if not validate.SHA_RE.match(ref):
                    offenders.append(f"{path.name}: {uses}")
    assert not offenders, "unpinned actions:\n" + "\n".join(offenders)


def test_every_reusable_workflow_has_an_example():
    shipped = {p.stem for p in REUSABLE}
    referenced = set()
    for path in (ROOT / "examples").glob("*.yml"):
        for uses in validate._iter_uses(_load(path)):
            if uses.startswith(validate.REPO_SLUG):
                referenced.add(uses.split("@", 1)[0].split("/")[-1].removesuffix(".yml"))
    missing = shipped - referenced
    assert not missing, f"no example caller for: {sorted(missing)}"
