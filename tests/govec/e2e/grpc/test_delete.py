from collections.abc import Callable

import pytest

from govec.client import GoVecClient
from govec.exceptions import GoVecAPIError
from govec.models import InsertRequest


@pytest.mark.e2e
def test_delete__existing_vector__returns_true(
    govec_grpc_client: GoVecClient,
    inserted_vector: Callable[..., InsertRequest],
) -> None:
    # Arrange
    request = inserted_vector()

    # Act
    result = govec_grpc_client.delete(request.id)

    # Assert
    assert result is True


@pytest.mark.e2e
def test_delete__missing_vector__raises_api_error(
    govec_grpc_client: GoVecClient,
) -> None:
    # Arrange
    missing_id = "grpc-definitely-not-inserted"

    # Act / Assert
    with pytest.raises(GoVecAPIError):
        govec_grpc_client.delete(missing_id)


@pytest.mark.e2e
def test_delete__missing_vector__error_is_labelled_grpc_not_http(
    govec_grpc_client: GoVecClient,
) -> None:
    # Arrange / Act
    with pytest.raises(GoVecAPIError) as excinfo:
        govec_grpc_client.delete("grpc-definitely-not-inserted-label-check")

    # Assert -- the code is a gRPC status, so calling it HTTP is wrong.
    assert excinfo.value.status_label == "gRPC"
    assert "HTTP" not in str(excinfo.value)
