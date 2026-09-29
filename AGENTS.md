# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`govec` is a Python client library for the [GoVec](https://github.com/your-org/govec) vector database, managed with `uv`. Python 3.13 is required (pinned in `.python-version`).

The client (`GoVecClient`) supports inserting dense + sparse vectors, similarity search, retrieval by ID, stats, flush, and delete. Transport is REST-only (`httpx`); gRPC is stubbed but not yet implemented.

## Commands

```bash
uv sync # Install dependencies and set up environment
task fmt # Format code
task fmt-check # Check formatting and types (ruff + ty)
uv add <package> # Add a dependency
uv build # Build the package
task server:health # Check GoVec server is running (required before e2e tests)
task test:e2e # Run e2e tests (requires GoVec server on localhost:8000)
```

## Structure

- `src/govec/` — library source, using `src` layout
  - `client.py` — `GoVecClient` (main public API)
  - `models.py` — request/response Pydantic-style models
  - `exceptions.py` — `GoVecError`, `GoVecAPIError`, `GoVecConnectionError`
  - `transport/` — transport backends (`rest.py`, `grpc.py` stub)
- `tests/govec/e2e/` — end-to-end tests (require a running server)
- `Taskfile.yaml` — task definitions (`fmt`, `fmt-check`, `server:health`, `test:e2e`)
- `pyproject.toml` — project metadata and build config (build backend: `uv_build`)
- `uv.lock` — lockfile, always commit this
- `py.typed` marker is present, so the package ships type hints

## Notes

- Build backend is `uv_build`, which only discovers packages under `src/`. Keep library code under `src/govec/`.
- `pytest` is already configured (test group). E2e tests are marked with `@pytest.mark.e2e` and require a live GoVec server on `localhost:8000`.
- gRPC transport raises `NotImplementedError` — do not use until implemented.
- On client init, a preflight handshake fetches server config (`dimensions`, `enable_mmap`). Dimension validation happens at insert time when `enable_mmap` is enabled.
