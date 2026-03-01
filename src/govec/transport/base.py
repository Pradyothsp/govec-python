from abc import ABC, abstractmethod

from govec.models import GoVecResponse, InfoResponse, InsertRequest, InsertResponse


class BaseTransport(ABC):
    @abstractmethod
    def server_info(self) -> GoVecResponse[InfoResponse | None]: ...

    @abstractmethod
    def insert(
        self, request: InsertRequest
    ) -> GoVecResponse[InsertResponse | None]: ...
