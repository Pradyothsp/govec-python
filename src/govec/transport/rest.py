from dataclasses import asdict

import httpx

from govec.models import GoVecResponse, InfoResponse, InsertRequest, InsertResponse

from govec.transport.base import BaseTransport


class RESTTransport(BaseTransport):
    def __init__(
        self, host: str, port: int, api_key: str | None = None, tls: bool = True
    ):
        scheme = "https" if tls else "http"
        self.base_url = f"{scheme}://{host}:{port}/api/v1"
        self.headers = {"Content-Type": "application/json"}

        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        # Using a persistent client session for connection pooling (much faster!)
        self.client = httpx.Client(headers=self.headers, timeout=10.0)

    def server_info(self) -> GoVecResponse[InfoResponse | None]:
        response = self.client.get(f"{self.base_url}/info")

        response_json = response.json()

        if response.status_code != 200:
            return GoVecResponse(
                success=response_json["success"],
                data=None,
                error=response_json.get("error", ""),
            )

        return GoVecResponse(
            success=response_json["success"], data=InfoResponse(**response_json["data"])
        )

    def insert(self, request: InsertRequest) -> GoVecResponse[InsertResponse | None]:
        response = self.client.post(f"{self.base_url}/vectors", json=asdict(request))

        response_json = response.json()

        if response.status_code != 201:
            return GoVecResponse(
                response_json["success"],
                data=response_json["data"],
                error=response_json["error"],
            )

        return GoVecResponse(
            success=response_json["success"],
            data=InsertResponse(**response_json["data"]),
        )
