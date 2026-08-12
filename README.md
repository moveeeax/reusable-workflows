# reusable-workflows

[![CI](https://github.com/moveeeax/reusable-workflows/actions/workflows/ci.yml/badge.svg)](https://github.com/moveeeax/reusable-workflows/actions/workflows/ci.yml)
[![Language](https://img.shields.io/badge/language-YAML-blue.svg)](https://yaml.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> Stop copy-pasting CI. One hardened, versioned library of composable GitHub **reusable workflows** — build, test, scan, release — that any repo calls in three lines.

Every workflow here is `workflow_call`-able, ships with documented inputs, and pins **every** third-party action to a full commit SHA. A caller repo gets a maintained pipeline without vendoring hundreds of lines of YAML.

## Workflows

| Workflow | Purpose | Key inputs |
| --- | --- | --- |
| [`go.yml`](.github/workflows/go.yml) | golangci-lint + `go build` + `go test -race` | `go-version`, `test-args`, `lint` |
| [`python.yml`](.github/workflows/python.yml) | ruff + pytest across a version matrix | `python-versions`, `install`, `test-command` |
| [`terraform.yml`](.github/workflows/terraform.yml) | `fmt -check` + `init` + `validate` | `terraform-version`, `working-directory`, `backend` |
| [`docker.yml`](.github/workflows/docker.yml) | Buildx build + optional push with OCI tags/labels | `image`, `platforms`, `push` |
| [`sbom.yml`](.github/workflows/sbom.yml) | Syft SBOM for a dir or image, uploaded as an artifact | `path`, `image`, `format` |
| [`release.yml`](.github/workflows/release.yml) | GitHub Release for a tag with auto-notes | `files`, `prerelease`, `generate-notes` |

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
      go-version: "1.23"
```

Ready-to-copy callers for every workflow live in [`examples/`](examples/).

## How it works

Each file under `.github/workflows/` (except this repo's own `ci.yml`) is a **reusable workflow**: it declares `on.workflow_call` with typed, described inputs, so a caller passes only what it needs and inherits the rest. Pipelines request the narrowest `permissions` they can (`contents: read` for lint/test, `packages: write` only for image pushes, `contents: write` only for releases).

Third-party actions are pinned to immutable commit SHAs, e.g.:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
```

so a moved tag can't change what runs in your pipeline.

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
OK: 13 workflow file(s) validated, 0 errors.
$ pytest -q
........................                                                 [100%]
```

## Versioning

Callers should pin to a major tag (`@v1`) for automatic patch/minor updates, or to a full SHA for maximum determinism. Releases are cut with [`release.yml`](.github/workflows/release.yml) and carry auto-generated notes.

## License

MIT — see [LICENSE](LICENSE).
