# reusable-workflows

[![CI](https://github.com/moveeeax/reusable-workflows/actions/workflows/ci.yml/badge.svg)](https://github.com/moveeeax/reusable-workflows/actions/workflows/ci.yml)
[![Language](https://img.shields.io/badge/language-YAML-blue.svg)](https://yaml.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> Stop copy-pasting CI. One hardened, versioned library of composable GitHub **reusable workflows** — build, test, scan, release — that any repo calls in three lines.

Every workflow here is `workflow_call`-able, ships with documented inputs, and pins **every** third-party action to a full commit SHA. A caller repo gets a maintained pipeline without vendoring hundreds of lines of YAML.

## Workflows

| Workflow | Purpose | Key inputs |
| --- | --- | --- |
| [`go.yml`](.github/workflows/go.yml) | golangci-lint + `go build` + `go test -race` | `go-version`, `test-args`, `lint`, `golangci-version` |
| [`python.yml`](.github/workflows/python.yml) | ruff + pytest across a version matrix | `python-versions`, `install`, `test-command`, `ruff-version` |
| [`terraform.yml`](.github/workflows/terraform.yml) | `fmt -check` + `init` + `validate` | `terraform-version`, `working-directory`, `backend` |
| [`docker.yml`](.github/workflows/docker.yml) | Buildx build + optional push with OCI tags/labels | `image`, `platforms`, `push` |
| [`sbom.yml`](.github/workflows/sbom.yml) | Syft SBOM for a dir or image, uploaded as an artifact | `path`, `image`, `format` |
| [`release.yml`](.github/workflows/release.yml) | GitHub Release for a tag with auto-notes | `files`, `prerelease`, `generate-notes` |
| [`audit.yml`](.github/workflows/audit.yml) | zizmor audit of the caller's workflows, SARIF to code scanning | `min-severity`, `fail-on-findings`, `upload-sarif`, `zizmor-version` |

## Usage

Reference a workflow by tag from any repo. A minimal Go pipeline:

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  ci:
    uses: moveeeax/reusable-workflows/.github/workflows/go.yml@v1
    with:
      go-version: "1.27"
```

Ready-to-copy callers for every workflow live in [`examples/`](examples/).

## Auditing your own workflows

`audit.yml` runs [zizmor](https://docs.zizmor.sh/) (pinned, default `1.31.1`) over the caller's repository: workflows, composite actions and Dependabot config. It reports template injection, over-broad `permissions`, persisted checkout credentials, unpinned actions and the other [zizmor audits](https://docs.zizmor.sh/audits/).

```yaml
jobs:
  audit:
    permissions:
      contents: read
      security-events: write
      actions: read
    uses: moveeeax/reusable-workflows/.github/workflows/audit.yml@v1
    with:
      min-severity: medium
```

- With `upload-sarif: true` (default) findings are uploaded to code scanning and show up in the Security tab. This needs code scanning on the repo: free for public repos, GitHub Advanced Security for private ones. The calling job must grant `security-events: write`; `actions: read` is only used in private repos.
- With `upload-sarif: false` findings are printed as job annotations and nothing is uploaded. Use it for private repos without code scanning and for pull requests from forks, whose token cannot write security events (see [`examples/audit-consumer.yml`](examples/audit-consumer.yml)).
- `fail-on-findings: true` (default) fails the job when at least one finding at or above `min-severity` (default `low`) remains after zizmor's ignore comments and `zizmor.yml` config. With `false` the job passes and adds a warning. In annotation mode zizmor's exit code cannot tell findings from a crash, so with `fail-on-findings: false` an error is also only a warning.
- zizmor picks up a `zizmor.yml` or `.github/zizmor.yml` in the caller's repo for per-rule ignores.

## How it works

Each file under `.github/workflows/` (except this repo's own `ci.yml`) is a **reusable workflow**: it declares `on.workflow_call` with typed, described inputs, so a caller passes only what it needs and inherits the rest. Pipelines request the narrowest `permissions` they can (`contents: read` for lint/test, `packages: write` for `docker.yml`, `security-events: write` for `audit.yml`, `contents: write` only for releases). Permissions in Actions cannot depend on an input, so `docker.yml` requests `packages: write` even when `push` is false, and the calling job has to grant it.

Third-party actions are pinned to immutable commit SHAs, e.g.:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

so a moved tag can't change what runs in your pipeline. Dependabot (`.github/dependabot.yml`) proposes pin updates weekly.

## Guarantees (enforced in CI)

`tools/validate.py` fails the build unless, for every workflow and example:

- reusable workflows expose `on.workflow_call`;
- every `workflow_call` input has a `description`;
- every third-party `uses:` is pinned to a 40-character commit SHA;
- every workflow declares an explicit `permissions` block;
- every example caller references a workflow that actually ships here.

Run it locally:

```console
$ pip install -r requirements.txt
$ python3 tools/validate.py
OK: 15 workflow file(s) validated, 0 errors.
$ pytest -q
..........................                                               [100%]
```

## Breaking changes since v1

This set of changes is not backward compatible for every caller:

- `go.yml` now runs golangci-lint v2 (default `golangci-version: v2.15.0`) through golangci-lint-action v9, which only supports v2. golangci-lint v2 uses a new config format: a `.golangci.yml` written for v1 fails to load. Add `version: "2"` and migrate the file with `golangci-lint migrate` (see the [v2 migration guide](https://golangci-lint.run/docs/product/migration-guide/)). Passing `golangci-version: v1.x` no longer works.
- `go.yml` defaults to Go `1.27` (was `1.23`). Pass `go-version` to keep an older toolchain.
- `terraform.yml` defaults to Terraform `1.17.1` (was `1.9.5`) and uses setup-terraform v4. Pass `terraform-version` if your code or state requires an older release.
- `python.yml` installs a pinned ruff (`ruff-version`, default `0.17.3`) instead of whatever is latest. New ruff releases no longer change lint results silently; bump the input to pick them up.
- All pinned actions moved to their current major versions (checkout v7, setup-go v7, setup-python v7, upload-artifact v7, build-push-action v7, setup-buildx-action v4, login-action v4, metadata-action v6, action-gh-release v3). They run on Node 24, so self-hosted runners must be recent enough to support it.
- Every `actions/checkout` step sets `persist-credentials: false` ([zizmor artipacked](https://docs.zizmor.sh/audits/#artipacked)). The job token is no longer left in `.git/config`, so a `git fetch` or `git push` inside `python.yml`'s `install`/`test-command` against a private repo no longer authenticates. None of the workflows push with git themselves; `release.yml` and `docker.yml` get their tokens through action inputs.
- `go.yml` passes `test-args` to `go test` without a shell ([zizmor template-injection](https://docs.zizmor.sh/audits/#template-injection)). The value is split with POSIX shell quoting rules (`-run 'TestA|TestB' ./...` still works), but `$VAR`, globs, `~`, `;` and `$(...)` are no longer expanded: they reach `go test` as literal arguments.
- `python.yml` still runs `install` and `test-command` as bash commands (that is what the inputs are for), now read from an env var and `eval`ed instead of being spliced into the step script. Treat both as code: never build them from untrusted context such as PR titles or branch names.

## Versioning

Callers should pin to a major tag (`@v1`) for automatic patch/minor updates, or to a full SHA for maximum determinism. Releases are cut with [`release.yml`](.github/workflows/release.yml) and carry auto-generated notes.

## License

MIT — see [LICENSE](LICENSE).
