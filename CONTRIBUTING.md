# Contributing to the GoVec Python SDK

Thanks for your interest. Bug reports and fixes are welcome. For a new feature, open an issue
first: the SDK mirrors the [GoVec server](https://github.com/Pradyothsp/govec) API, so most
features start there.

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/), [Task](https://taskfile.dev/installation/),
and Docker for the e2e tests.

```bash
git clone https://github.com/Pradyothsp/govec-python.git
cd govec-python

uv sync --all-groups      # dependencies, including dev and test groups
uv run pre-commit install # ruff, ty and file hygiene on every commit

task test                 # unit tests; no server needed
```

## Running the e2e tests

The e2e suites run every operation against a real server, over REST and over gRPC:

```bash
docker run -d -p 9697:9697 -p 9698:9698 -e GOVEC_GRPC_ENABLED=true ghcr.io/pradyothsp/govec:0.1.0
task test:e2e
```

## Everyday commands

| Command | What it does |
|---|---|
| `task test` | Unit tests |
| `task test:e2e` | REST, then gRPC e2e tests |
| `task fmt` | Format and autofix with ruff |
| `task fmt:check` | ruff, ty and format check, as CI runs them |
| `task proto:gen` | Regenerate the gRPC stubs after copying in a new server proto |
| `uv build` | Build the sdist and wheel |

## Project conventions

[AGENTS.md](AGENTS.md) describes how the code is organized and the rules it follows. The
essentials:

- **REST and gRPC must behave identically** behind `GoVecClient`. A change to one transport
  needs the same change in the other, and tests in both e2e suites.
- **Build responses field by field**, never `Model(**json)`, so newer servers can add fields
  without breaking the SDK.
- **Only `GoVecError` subclasses reach callers;** transports translate `httpx` and `grpc`
  failures.
- **Never hand-edit the generated stubs** in `src/govec/proto/`.

## Submitting a pull request

1. `task fmt:check` and `task test` pass, plus `task test:e2e` if you touched a transport.
2. New behaviour has tests; bug fixes have a regression test.
3. User-visible changes are reflected in `README.md`.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), e.g.
`fix: ...` or `feat: ...`. Keep each PR to one logical change.

## License

By contributing, you agree that your contributions are licensed under the project's
[Apache-2.0 license](LICENSE).
