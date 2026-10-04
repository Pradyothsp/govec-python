# GoVec Python SDK

The Python client for [GoVec](https://github.com/Pradyothsp/govec), a compact vector search
engine with HNSW, int8 quantization and hybrid search. Talk to it over REST or gRPC through
the same API.

[![CI](https://github.com/Pradyothsp/govec-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Pradyothsp/govec-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/govec)](https://pypi.org/project/govec/)
[![Python](https://img.shields.io/pypi/pyversions/govec)](https://pypi.org/project/govec/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

## Features

- **The whole server API:** insert, batch insert, search with metadata filters and hybrid
  dense + sparse scoring, get, delete, stats, info, flush and reset.
- **REST or gRPC, one argument apart.** Both return the same results and raise the same
  exceptions; the test suite runs every operation against a real server over both.
- **Typed.** Responses are dataclasses, and the package ships `py.typed`.
- **Batch inserts that scale:** large lists are chunked for you, with per-vector errors
  reported instead of failing the whole batch.
- **Safe against newer servers.** Fields a newer GoVec adds are ignored, not fatal.

## Installation

```bash
pip install govec
# or
uv add govec
```

Requires Python 3.12 or newer. You also need a GoVec server; the quickest way is Docker:

```bash
docker run -p 9697:9697 -v govec-data:/data ghcr.io/pradyothsp/govec:latest
```

## Quick start

```python
from govec import GoVecClient

with GoVecClient(host="localhost", port=9697, api_key="", protocol="rest", tls=False) as client:
    client.insert(vector_id="doc-1", dense_vector=[0.12, 0.91, 0.20], metadata={"title": "Getting started"})
    client.insert(vector_id="doc-2", dense_vector=[0.80, 0.10, 0.31], metadata={"title": "Release notes"})

    for hit in client.search(dense_vector=[0.10, 0.88, 0.18], k=2):
        print(hit.id, round(hit.score, 3), hit.meta)
```

```text
doc-1 1.0 {'title': 'Getting started'}
doc-2 0.287 {'title': 'Release notes'}
```

In a real application the vectors come from an embedding model (OpenAI, Sentence
Transformers, ...); GoVec stores and searches them. Every vector in an index must have the
same number of dimensions.

## Connecting

```python
GoVecClient(host, port, api_key, protocol, tls=True)
```

| Argument | Meaning |
|---|---|
| `host`, `port` | Where the server listens. GoVec's defaults are **9697** for REST and **9698** for gRPC. |
| `api_key` | The server's `server.api_key`, sent as a bearer token. Pass `""` when auth is off (the default). |
| `protocol` | `"rest"` or `"grpc"`. gRPC must be enabled on the server (`GOVEC_GRPC_ENABLED=true`). |
| `tls` | `True` (default) for `https`/TLS; pass `False` for a plain local server. |

The constructor contacts the server straight away, so a wrong address fails at
`GoVecClient(...)` rather than on the first call.

To use gRPC, change two arguments; nothing else in your code changes:

```python
with GoVecClient(host="localhost", port=9698, api_key="", protocol="grpc", tls=False) as client:
    ...
```

### Closing the client

A client holds an open connection, so close it when you're done. How depends on how long
you need it.

**For scripts, jobs, notebooks and tests, use a context manager.** The connection is closed
when the block ends, even if an exception is raised:

```python
with GoVecClient(host="localhost", port=9697, api_key="", protocol="rest", tls=False) as client:
    client.search(dense_vector=[0.10, 0.88, 0.18], k=5)
```

**For long-running services, create one client at startup, reuse it, and close it at
shutdown.** Don't open a client per request: each one repeats the startup handshake and a
new connection. With FastAPI, for example:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from govec import GoVecClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.govec = GoVecClient(host="localhost", port=9697, api_key="", protocol="rest", tls=False)
    yield
    app.state.govec.close()


app = FastAPI(lifespan=lifespan)
```

`close()` is safe to call more than once.

## Guide

The examples below use a connected `client`, as in the quick start.

### Inserting vectors

```python
client.insert(vector_id="doc-1", dense_vector=[0.12, 0.91, 0.20], metadata={"lang": "en", "year": 2024})
```

Inserting an existing ID replaces it. For many vectors, build `InsertRequest`s and use
`insert_many`, which sends them in chunks of `batch_size`:

```python
from govec import InsertRequest

result = client.insert_many(
    [InsertRequest(id=f"doc-{i}", vector=vec) for i, vec in enumerate(vectors)],
    batch_size=500,
)
print(result.inserted_count)
for failure in result.errors:
    print(failure.id, failure.error)
```

### Searching

```python
hits = client.search(dense_vector=[0.10, 0.88, 0.18], k=5)
```

Each hit has `id`, `score` (higher is closer) and `meta` (`None` if the vector has no
metadata).

**Filter by metadata.** Every key must match exactly:

```python
client.search(dense_vector=[0.10, 0.88, 0.18], k=5, filter={"lang": "en"})
```

**Hybrid search.** Add a sparse vector (for example from BM25 or SPLADE) to both the insert
and the query; the server blends the dense and sparse scores:

```python
from govec import SparseVector

client.insert(
    vector_id="doc-3",
    dense_vector=[0.3, 0.3, 0.3],
    sparse_vector=SparseVector(indices=[7, 42], values=[1.0, 0.5]),
)
client.search(
    dense_vector=[0.3, 0.3, 0.3],
    sparse_vector=SparseVector(indices=[42], values=[1.0]),
    k=3,
)
```

### Reading and deleting

```python
record = client.get_by_id(vector_id="doc-1")   # vector, sparse_vector and metadata, or None if missing
client.delete(vector_id="doc-1")               # raises GoVecAPIError if the ID doesn't exist
```

### Administration

```python
client.info()        # server version, index type, quantization, metric, dimensions
client.get_stats()   # number of stored vectors
client.health()      # liveness
client.flush()       # write a snapshot to disk now
client.reset()       # delete every vector -- irreversible
```

## API reference

| Method | Returns |
|---|---|
| `insert(vector_id, dense_vector, sparse_vector=None, metadata=None)` | `True` |
| `insert_many(requests, batch_size=500)` | `BatchInsertResponse`: `inserted_count`, `errors` |
| `search(dense_vector=None, sparse_vector=None, k=10, filter=None)` | `list[SearchResponse]`: `id`, `score`, `meta` |
| `get_by_id(vector_id)` | `GetByIdResponse` or `None` |
| `delete(vector_id)` | `True` |
| `info()` | `InfoResponse`: `version`, `index_type`, `quantization`, `distance_metric`, `dimensions`, `vector_count`, `enable_mmap` |
| `get_stats()` | `GetStatsResponse`: `vector_count` |
| `health()` / `flush()` / `reset()` | a response with `status` |
| `close()` | closes the connection; safe to call twice |

## Error handling

Both transports raise the same exceptions, all subclasses of `GoVecError`:

| Exception | Raised when |
|---|---|
| `GoVecAPIError` | the server rejected the request, e.g. a vector with the wrong dimensions. `message` says why; `status_code` is the HTTP status over REST and the gRPC status code over gRPC. |
| `GoVecConnectionError` | the server can't be reached |
| `GoVecTimeoutError` | the server didn't answer in time (10 s per request, 60 s for a gRPC batch insert); a smaller `k` or a narrower filter often helps |
| `GoVecClientClosedError` | the client was used after `close()` |

```python
from govec import GoVecAPIError, GoVecError

try:
    client.insert(vector_id="doc-9", dense_vector=[0.1, 0.2])   # wrong width for a 3-dimensional index
except GoVecAPIError as e:
    print(e.status_code, e.message)
except GoVecError:
    ...                                  # connection problems, timeouts
```

## Compatibility

| SDK | GoVec server | Python |
|---|---|---|
| 0.1.x | 0.1.0 and newer | 3.12 – 3.14 |

`client.info().version` tells you which server release you're connected to.

Two transport differences to know, both from protobuf:

- **Metadata numbers come back as floats over gRPC:** `{"year": 2024}` returns as
  `2024.0`. REST preserves integers.
- **Vectors come back at 32-bit precision over gRPC:** GoVec stores 32-bit floats, so
  `get_by_id` over gRPC returns `0.12` as `0.11999999731779099`. REST rounds it back to
  `0.12`.

## Roadmap

- **Async client** (planned for 0.2.0): an `AsyncGoVecClient` with the same API over
  `httpx.AsyncClient` and `grpc.aio`, for FastAPI services and async RAG pipelines. Until
  then, call the sync client from async code with `await asyncio.to_thread(client.search, ...)`.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache License 2.0](LICENSE)
