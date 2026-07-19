# reusable-workflows

> Stop copy-pasting CI: one hardened, versioned workflow library.

**Status:** 🚧 In development

## Overview

A library of composable, opinionated GitHub reusable workflows (build/test/scan/release).

## Features

- Reusable jobs: lint, test, container build+push, SBOM, release
- Security defaults: least-priv tokens, pinned actions
- Language starters (Go, Python, Terraform)
- Inputs documented, semantic-versioned
- Example callers for each

## Stack

GitHub reusable workflows (workflow_call) + composite actions.

## Usage

```yaml
jobs:
  ci:
    uses: moveeeax/reusable-workflows/.github/workflows/go.yml@v1
```

## License

MIT
