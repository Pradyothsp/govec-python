from govec.models import GoVecResponse, InfoResponse
from govec.transport.base import BaseTransport


class GRPCTransport(BaseTransport):
    def server_info(self) -> GoVecResponse[InfoResponse | None]: ...
