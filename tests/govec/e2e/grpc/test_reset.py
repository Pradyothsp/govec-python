import pytest

from govec.client import GoVecClient


@pytest.mark.e2e
def test_reset__no_such_rpc_in_the_server__raises_not_implemented(
    govec_grpc_client: GoVecClient,
) -> None:
    # Arrange / Act / Assert -- the proto defines no Reset RPC, unlike REST
    with pytest.raises(NotImplementedError):
        govec_grpc_client.reset()
