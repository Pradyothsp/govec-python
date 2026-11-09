"""Building blocks for faking GoVec's REST API with respx.

The `server` fixture in `tests/conftest.py` routes requests for `BASE_URL`;
tests add a route per endpoint they exercise and answer it with these.
"""

import httpx

HOST = "testserver"
PORT = 9697
BASE_URL = f"http://{HOST}:{PORT}"


def ok(data: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json={"success": True, "data": data})


def error(status_code: int, message: str) -> httpx.Response:
    return httpx.Response(status_code, json={"success": False, "error": message})


def info(
    *, dimensions: int = 3, enable_mmap: bool = False, version: str = "dev"
) -> dict[str, object]:
    return {
        "quantization": "none",
        "index_type": "brute",
        "distance_metric": "cosine",
        "dimensions": dimensions,
        "vector_count": 0,
        "enable_mmap": enable_mmap,
        "version": version,
    }
