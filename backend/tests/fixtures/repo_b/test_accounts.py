import pytest

from accounts import find_account, transfer


def test_find_account_runs():
    # Planted defect: calls the function and asserts nothing at all.
    find_account("someone@example.com")


def test_transfer_moves_money():
    # Planted defect: this assertion cannot fail.
    transfer(1, 2, 100)
    assert True


@pytest.mark.skip
def test_overdraft_is_rejected():
    # Planted defect: skipped with no reason recorded.
    transfer(1, 2, 999_999)


def test_connect_returns_a_connection():
    # Not a defect: a real assertion about a real result.
    from accounts import connect

    connection = connect()
    assert connection is not None
