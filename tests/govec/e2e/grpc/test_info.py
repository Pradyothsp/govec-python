import pytest

from govec.client import GoVecClient


@pytest.mark.e2e
def test_server_info__server_running__returns_server_config(
    govec_grpc_client: GoVecClient,
) -> None:
    # Arrange / Act
    info = govec_grpc_client.info()

    # Assert
    assert info.index_type in ("brute", "hnsw")
    assert info.distance_metric in ("cosine", "euclidean")
    assert info.vector_count >= 0


@pytest.mark.e2e
def test_server_info__server_has_mmap_enabled__reports_it_over_grpc(
    govec_grpc_client: GoVecClient, govec_e2e_client: GoVecClient
) -> None:
    # Arrange -- REST is the reference: both read the same server config.
    expected = govec_e2e_client.info().enable_mmap
    if not expected:
        # Without this guard the test is vacuous: gRPC used to hardcode False,
        # so against a server with mmap off it passed whether the value was
        # read from the server or invented. Skipping says so out loud rather
        # than reporting green for a case it cannot actually distinguish.
        pytest.skip("server has enable_mmap off; run with enable_mmap: true to cover")

    # Act
    actual = govec_grpc_client.info().enable_mmap

    # Assert -- hardcoded False before InfoResponse carried the field, which
    # silently disabled the client's own dimension check over gRPC.
    assert actual is True


@pytest.mark.e2e
def test_server_info__version__matches_what_rest_reports(
    govec_grpc_client: GoVecClient, govec_e2e_client: GoVecClient
) -> None:
    # Arrange -- REST is the reference: both read the same running binary.
    expected = govec_e2e_client.info().version

    # Act
    actual = govec_grpc_client.info().version

    # Assert
    assert expected
    assert actual == expected
