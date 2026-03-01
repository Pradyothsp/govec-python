from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MAX_UINT32 = 4_294_967_295


@dataclass
class GoVecResponse[T]:
    success: bool
    data: T
    error: str | None = None


@dataclass
class StatsResponse:
    vector_count: int


IndexType = Literal["hnsw", "brute_force"]
DistanceMetric = Literal["cosine"]


@dataclass
class InfoResponse:
    quantization: str
    index_type: IndexType
    distance_metric: DistanceMetric
    dimensions: int
    vector_count: int


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
class InsertRequest:
    id: str
    vector: list[float]
    sparse_vector: SparseVector
    metadata: dict[str, str] | None = None

    def __post_init__(self):
        if not self.id:
            raise ValueError("Document ID cannot be empty.")


@dataclass
class InsertResponse:
    status: str
