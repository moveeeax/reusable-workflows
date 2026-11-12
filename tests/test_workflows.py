"""Unit tests for the reusable-workflow library.

These map one-to-one onto the acceptance criteria in the project spec:

* each workflow is callable via ``workflow_call`` with documented inputs;
* all third-party actions are pinned by commit SHA;
* an example consumer workflow is provided for each reusable workflow.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess

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
                     "sbom.yml", "release.yml", "audit.yml"):
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


def test_audit_workflow_contract():
    doc = _load(WF_DIR / "audit.yml")
    inputs = validate._on_block(doc)["workflow_call"]["inputs"]
    for name in ("min-severity", "fail-on-findings", "upload-sarif", "zizmor-version"):
        assert name in inputs, f"audit.yml lacks input {name}"
    assert inputs["fail-on-findings"]["type"] == "boolean"
    # zizmor must be pinned to an exact version, never "latest".
    assert re.fullmatch(r"\d+\.\d+\.\d+", inputs["zizmor-version"]["default"])
    # SARIF upload to code scanning needs security-events: write.
    assert doc["permissions"].get("security-events") == "write"
    assert doc["permissions"].get("contents") == "read"
    steps = doc["jobs"]["audit"]["steps"]
    zizmor = next(s for s in steps if s.get("uses", "").startswith("zizmorcore/zizmor-action@"))
    assert zizmor["with"]["version"] == "${{ inputs.zizmor-version }}"
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


ALL_WORKFLOWS = sorted(WF_DIR.glob("*.yml"))


def _steps(doc: dict):
    for job in (doc.get("jobs") or {}).values():
        yield from job.get("steps") or []


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda p: p.name)
def test_checkout_does_not_persist_credentials(path: Path):
    # zizmor artipacked: no workflow here pushes with git, so the checkout
    # token must not be left in .git/config for later steps to pick up.
    for step in _steps(_load(path)):
        if step.get("uses", "").startswith("actions/checkout@"):
            assert (step.get("with") or {}).get("persist-credentials") is False, path.name


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda p: p.name)
def test_run_scripts_have_no_template_expansions(path: Path):
    # zizmor template-injection: inputs and contexts reach run scripts through
    # env, never as ${{ }} spliced into the script text.
    for step in _steps(_load(path)):
        assert "${{" not in step.get("run", ""), f"{path.name}: {step.get('name')}"


def test_ci_calls_audit_with_self_repository_syntax_and_fails_on_findings():
    audit = _load(WF_DIR / "ci.yml")["jobs"]["audit"]
    assert audit["uses"] == "$/.github/workflows/audit.yml"
    assert audit["with"]["fail-on-findings"] is True


def test_dependabot_has_a_cooldown():
    doc = _load(ROOT / ".github" / "dependabot.yml")
    for update in doc["updates"]:
        assert update.get("cooldown", {}).get("default-days", 0) >= 7


def _run_go_test_step(tmp_path: Path, test_args: str) -> list[str]:
    """Run go.yml's Test step script with a fake `go` that records its argv."""
    fake = tmp_path / "go"
    fake.write_text('#!/bin/sh\nfor a in "$@"; do printf \'%s\\n\' "$a"; done\n')
    fake.chmod(0o755)
    step = next(s for s in _steps(_load(WF_DIR / "go.yml")) if s.get("name") == "Test")
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
           **{k: test_args for k in step["env"]}}
    out = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env,
                         check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def test_go_test_args_are_split_without_a_shell(tmp_path: Path):
    assert _run_go_test_step(tmp_path, "-race -covermode=atomic -coverprofile=coverage.out ./...") == [
        "test", "-race", "-covermode=atomic", "-coverprofile=coverage.out", "./..."]
    # Quoting still groups words, as it did when the input was spliced in.
    assert _run_go_test_step(tmp_path, "-run 'TestA|TestB' ./...") == [
        "test", "-run", "TestA|TestB", "./..."]
    # Shell syntax reaches go test as literal arguments and runs nothing.
    assert _run_go_test_step(tmp_path, "./... ; touch pwned $(touch pwned2)") == [
        "test", "./...", ";", "touch", "pwned", "$(touch", "pwned2)"]
    assert not (tmp_path / "pwned").exists() and not (tmp_path / "pwned2").exists()


@pytest.mark.parametrize("name", ["Install", "Test"])
def test_python_command_inputs_keep_shell_semantics(tmp_path: Path, name: str):
    # install and test-command are commands by contract; moving them into env
    # must not change how ||, quotes or failures behave.
    step = next(s for s in _steps(_load(WF_DIR / "python.yml")) if s.get("name") == name)
    (var,) = step["env"]

    def run(cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path,
                              env={**os.environ, var: cmd}, capture_output=True, text=True)

    ok = run("false || echo 'fell back'")
    assert ok.returncode == 0 and ok.stdout == "fell back\n"
    assert run("echo first; false").returncode != 0
