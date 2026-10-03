from dataclasses import dataclass
from typing import Any, Literal

MAX_UINT32 = 4_294_967_295  # (2³² - 1)


@dataclass
class StatsResponse:
    vector_count: int


# These must match what the server actually puts in /info -- see the constants
# in its internal/config/config.go. "brute_force" was never one of them; the
# server says "brute", so the only two values a real response can carry were
# one typo and one omission. Nothing failed at runtime because InfoResponse is
# built by splatting the JSON, with no validation -- the cost landed on anyone
# type-checking `info.index_type == "brute"`, which a checker called
# impossible.
IndexType = Literal["brute", "hnsw"]
DistanceMetric = Literal["cosine", "euclidean"]


@dataclass
class InfoResponse:
    quantization: str
    index_type: IndexType
    distance_metric: DistanceMetric
    dimensions: int
    vector_count: int
    enable_mmap: bool
    # The server release: the git tag it was built from, or "dev" for a local build.
    version: str


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]

    def __post_init__(self):
        if not self.indices or not self.values:
            raise ValueError("SparseVector cannot have empty indices or values.")

        if len(self.indices) != len(self.values):
            raise ValueError(
                f"Length mismatch: {len(self.indices)} indices vs {len(self.values)} values."
            )

        if min(self.indices) < 0 or max(self.indices) > MAX_UINT32:
            raise ValueError(
                f"Indices must be strictly between 0 and {MAX_UINT32} (uint32 bounds)."
            )


@dataclass
class GetStatsResponse:
    vector_count: int


@dataclass
class FlushResponse:
    status: str


@dataclass
class HealthResponse:
    status: str


@dataclass
class ResetResponse:
    status: str


@dataclass
class GetByIdResponse:
    id: str
    vector: list[float]
    # None for a dense-only record. SparseVector rejects empty indices/values,
    # so None is the only way to say "this record has no sparse component" --
    # both transports omit the field rather than sending an empty one.
    sparse_vector: SparseVector | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class InsertRequest:
    id: str
    vector: list[float]
    sparse_vector: SparseVector | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if not self.id:
            raise ValueError("Document ID cannot be empty.")


@dataclass
class InsertResponse:
    status: str


@dataclass
class BatchInsertError:
    id: str
    error: str


@dataclass
class BatchInsertResponse:
    inserted_count: int
    errors: list[BatchInsertError]


@dataclass
class SearchRequest:
    k: int = 50
    filter: dict[str, Any] | None = None
    sparse_vector: SparseVector | None = None
    vector: list[float] | None = None


@dataclass
class SearchResponse:
    id: str
    score: float
    # None when the vector carries no metadata. REST omits the key entirely in
    # that case and gRPC sends an empty map; both are normalised to None so the
    # two transports agree.
    meta: dict[str, Any] | None = None


@dataclass
class DeleteResponse:
    id: str
    status: str
