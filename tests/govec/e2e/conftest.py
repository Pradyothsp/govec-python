import pytest

from govec.client import GoVecClient


@pytest.fixture(scope="session")
def govec_e2e_client() -> GoVecClient:
    return GoVecClient(
        host="localhost", port=8000, api_key="", protocol="rest", tls=False
    )
