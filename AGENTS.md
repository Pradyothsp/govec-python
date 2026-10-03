# AGENTS.md

This file provides guidance to agents (Claude, Gemini) and developers working on the GoVec
Python client.

## Project

`govec` is the Python client library for [GoVec](https://github.com/Pradyothsp/govec), a
single-node vector database. Managed with `uv`. `requires-python` is `>=3.13`;
`.python-version` pins 3.14 for local development.

`GoVecClient` covers the server's whole surface: health, info, stats, flush, reset,
get-by-id, insert (dense + sparse + metadata), batch insert, search, and delete. Both
transports — REST (`httpx`) and gRPC — implement all of it, so switching `protocol=`
changes the wire format and nothing else.

## Commands

```bash
uv sync                # Install dependencies and set up the environment
task fmt               # Format and autofix with ruff
task check             # ruff check + ty + ruff format --check  (alias: fmt:check, fmt-check)
task proto:gen         # Regenerate protobuf + gRPC stubs from src/govec/proto/govec.proto
uv add <package>       # Add a dependency
uv build               # Build the package

task test              # Unit tests only -- no server needed  (alias: test:unit)
task test:e2e:rest     # REST e2e   -- needs govec on :9697
task test:e2e:grpc     # gRPC e2e   -- needs govec on :9698 with GOVEC_GRPC_ENABLED=true
task test:e2e          # Both e2e suites
task test:all          # Everything
```

Each e2e leaf task owns the precondition for the server it needs; the `test:e2e` and
`test:all` aggregates just chain the leaves, so there is one place to change a port.

## Structure

- `src/govec/` — library source, `src` layout
  - `client.py` — `GoVecClient`, the public API; picks a transport from `protocol=`
  - `models.py` — request/response dataclasses
  - `exceptions.py` — `GoVecError`, `GoVecAPIError`, `GoVecConnectionError`
  - `transport/`
    - `base.py` — `BaseTransport`, the ABC both transports must satisfy
    - `rest.py` — REST over `httpx`
    - `grpc.py` — gRPC over the generated stubs
    - `convert.py` — Python ↔ `google.protobuf.Value`; pure functions, no transport
      dependency, mirroring the server's own `internal/grpcserver/convert`
  - `proto/` — `govec.proto` (copied from the server repo) and its generated stubs
- `tests/govec/` — mirrors the source tree
  - `transport/` — unit tests for the modules under `src/govec/transport/`
  - `e2e/rest/`, `e2e/grpc/` — one file per operation, against a live server
  - `e2e/conftest.py` — client fixtures and `E2E_DIMENSIONS`
- `Taskfile.yaml`, `pyproject.toml` (build backend: `uv_build`), `uv.lock` — always commit
  the lockfile
- `py.typed` marker is present, so the package ships its type hints

## Notes

- Build backend is `uv_build`, which only discovers packages under `src/`. Keep library
  code under `src/govec/`.
- **The proto is a copy.** `src/govec/proto/govec.proto` is duplicated from the server's
  `proto/govec/v1/govec.proto`. After any server-side proto change, copy it over and run
  `task proto:gen` — nothing detects the drift for you.
- **Adding a transport method means three files.** The abstract method in `base.py`, then
  `rest.py` and `grpc.py`. `BaseTransport` is an ABC, so a missing implementation fails at
  instantiation rather than at call time.
- **Both transports must behave identically behind the client**, not just return the same
  type. `get_by_id` is the example: REST returns `None` for a 404, so the gRPC transport
  translates `NOT_FOUND` into `None` rather than raising. `search` is the other: a
  protobuf map is always present, so gRPC reports "no metadata" as an empty map where
  REST omits the key — the transport normalises it to `None` to match.
- E2e tests are marked per-test with `@pytest.mark.e2e`. `addopts = ["-m", "not e2e"]`
  deselects them by default, so a bare `pytest` runs the unit tests and needs no server.
- Both e2e suites share one server for a whole session, and the gRPC suite resets it
  mid-run. Every test must insert the data it asserts on.
- E2e vectors use `E2E_DIMENSIONS`, a constant — **not** `client.dimensions`. That value is
  fetched once during the preflight handshake and reads `0` on a server with no configured
  `engine.dimensions`, which silently turned tests into empty-vector inserts that passed
  vacuously.
- On client init, a preflight handshake fetches server config (`dimensions`,
  `enable_mmap`). The client-side dimension check in `insert` only runs when
  `enable_mmap` is on, and it is a convenience, not an authority — the server is the one
  that enforces width, and it answers `400`/`InvalidArgument` when a vector disagrees.
- **Ints do not survive gRPC.** protobuf `Struct` stores every number as a double, so
  metadata `{"year": 2024}` returns `2024.0`. REST (JSON) preserves the int. Pinned by a
  test so it cannot change silently.
