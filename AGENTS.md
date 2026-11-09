# AGENTS.md

Guidance for AI agents (Claude, Gemini) and contributors working in this repo: how the code is
organized, the rules it follows, and the traps to avoid. User-facing docs are in `README.md`.

## What this is

`govec` is the Python client for [GoVec](https://github.com/Pradyothsp/govec), a single-node
vector search engine. One `GoVecClient`, two transports: REST (`httpx`) and gRPC. Switching
`protocol=` must change the wire format and **nothing else**: same methods, same return
values, same exceptions. Most rules below exist to protect that.

The server is the authority. The SDK validates only what it can check cheaply and locally;
it never second-guesses the server's answers.

## Commands

| Command | Use |
|---|---|
| `uv sync --all-groups` | Set up the environment (dev and test groups included) |
| `task test` | Unit tests; no server needed |
| `task test:e2e` | REST then gRPC e2e suites; needs GoVec on `:9697` and `:9698` |
| `task fmt` / `task fmt:check` | Format and autofix / ruff + ty + format check |
| `task proto:gen` | Regenerate the gRPC stubs from `src/govec/proto/govec.proto` |
| `uv build` | Build the sdist and wheel into `dist/` |

A local server for the e2e suites:
`docker run -p 9697:9697 -p 9698:9698 -e GOVEC_GRPC_ENABLED=true ghcr.io/pradyothsp/govec:0.1.0`

## Code map

```text
src/govec/
  client.py          GoVecClient: the public API; picks a transport, runs the preflight handshake
  client_logic.py    width checks, batching and the delete check around transport calls; pure functions
  models.py          request/response dataclasses; input validation lives in __post_init__
  exceptions.py      GoVecError and its subclasses, the only exceptions callers should see
  transport/
    base.py          BaseTransport ABC: the contract both transports implement
    rest.py          REST over httpx
    rest_mappers.py  REST response -> model mappers and the status/envelope check; pure functions
    json_codec.py    request and response JSON (orjson), with the NaN/infinity check; pure functions
    grpc.py          gRPC over the generated stubs
    grpc_mappers.py  model <-> proto message mappers and gRPC error -> GoVec exception; pure functions
    convert.py       Python values <-> google.protobuf.Value; pure functions, no I/O
  proto/             govec.proto (a copy of the server's) and its generated stubs
tests/govec/
  test_client.py     client behaviour against a fake transport
  test_client_logic.py   the shared client rules, once for both clients
  transport/         unit tests per transport module; REST runs on httpx.MockTransport
  e2e/rest/, e2e/grpc/   one file per operation, against a live server
.github/workflows/   ci.yml (every push/PR), release.yml (v* tags -> PyPI)
```

## Conventions

**Transports must agree in behaviour, not just in types.** Where the wire formats differ,
the transport normalises. Examples: REST answers a missing vector with 404 and gRPC with
`NOT_FOUND`; both make `get_by_id` return `None`. REST omits `meta` when there is none and
gRPC sends an empty map; both become `None`.

**Adding an operation touches seven places:** the abstract method in `transport/base.py`,
its implementation in `rest.py` and `grpc.py`, its mappers in `rest_mappers.py` and
`grpc_mappers.py`, the method on `GoVecClient`, and an e2e test in *both* `e2e/rest/` and
`e2e/grpc/`. `BaseTransport` is an ABC, so a missing implementation fails at construction
rather than at call time.

**Wire details live in the mappers, not the models.** A transport method only sends; turning
a response into a model, a model into a proto request, or a gRPC error into a GoVec exception
happens in `rest_mappers.py` / `grpc_mappers.py`, so a sync and an async transport can share
it. The mappers are internal: not methods on the models, and not exported.

**Build responses field by field.** Never `Model(**json)`. Splatting turns every field a
newer server adds into a `TypeError` for every older SDK. Read the fields the model
declares, by name, and ignore the rest.

**Only GoVec exceptions escape.** Transports translate `httpx` and `grpc` failures into
`GoVecAPIError`, `GoVecConnectionError`, `GoVecTimeoutError` or `GoVecClientClosedError`.
A raw `httpx.ConnectError` or `grpc.RpcError` reaching a caller is a bug.

**The proto is a copy, and the stubs are generated.** `src/govec/proto/govec.proto`
duplicates the server's `proto/govec/v1/govec.proto`. After a server proto change, copy it
over and run `task proto:gen`; nothing detects drift for you. Never hand-edit
`govec_pb2*.py`. The stubs are committed because users can't run `protoc`.

**Typed and checked.** The package ships `py.typed`; `ty` must pass. The floor is Python
3.12 (the transports use `typing.override`; the tests use PEP 695 `type` aliases), and CI
runs 3.12, 3.13 and 3.14.

**Comments explain why.** The existing code records the bug or decision behind
non-obvious lines (see `exceptions.py`, `get_by_id`). Match that. The same goes for
docstrings: none on a function whose name and signature already say what it does
(`decode`, `encode_request`); write one only for what the code can't show, such as the
decision, bug or measurement behind it, a trap, or surprising behaviour.

## Testing

- Names read `test_<unit>__<condition>__<expected>`; bodies are marked Arrange / Act /
  Assert.
- REST unit tests use the `rest_transport` fixture (`transport/conftest.py`): the real
  transport over `httpx.MockTransport`, so request building and parsing are tested without
  a server.
- E2e tests carry `@pytest.mark.e2e`, and `addopts = ["-m", "not e2e"]` deselects them, so a
  bare `pytest` never needs a server. The e2e tasks pass `-m e2e`.
- Both e2e suites share one server for the session, and the gRPC suite resets it. **Every
  test inserts the data it asserts on.**
- E2e vectors use the `E2E_DIMENSIONS` constant, never `client.dimensions`: that reads `0`
  on a server without configured dimensions and made tests insert empty vectors that
  passed vacuously.
- A behaviour that differs by transport gets a test per transport, so the difference
  can't change silently.

## Traps

- **Integers don't survive gRPC.** protobuf `Struct` stores numbers as doubles, so metadata
  `{"year": 2024}` comes back as `2024.0` over gRPC. REST preserves it. Pinned by a test.
- **orjson writes NaN and infinity as `null`.** The server decodes `null` into a float32 as 0,
  so a NaN vector would be stored or searched as zeros with no error. `json_codec.py`
  checks requests before encoding and raises `ValueError`, as httpx's encoder did. Keep the
  check if you touch request encoding. orjson is there for speed: `json.dumps` of a
  1,536-float query cost ~1.1 ms of a ~5.4 ms search.
- **The constructor talks to the server.** `GoVecClient(...)` fetches `info` as a preflight
  handshake, so a wrong host fails there. If the handshake raises, the constructor closes the
  transport itself; the caller never got an object to close.
- **The client-side dimension check only runs with `enable_mmap` on.** It is a
  convenience; the server enforces width and answers 400 / `InvalidArgument`.
- **`tls` defaults to `True`.** Local servers need `tls=False`.
- **`uv_build` only finds packages under `src/`.** Keep library code in `src/govec/`.

## Releasing

Bump `version` in `pyproject.toml`, commit, then push a matching annotated tag
(`git tag -a v0.2.0 -m "govec v0.2.0"`). `release.yml` runs the full CI, refuses a tag that
doesn't match the version, publishes to PyPI via Trusted Publishing, and creates the GitHub
Release.

## Before you finish

1. `task fmt && task fmt:check`: ruff, ty and formatting are clean.
2. `task test`, plus `task test:e2e` against a local server if you touched a transport.
3. `uv.lock` is committed whenever dependencies change.
