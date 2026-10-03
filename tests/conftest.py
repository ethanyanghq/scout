import pytest

from scout.trip_store import TripStore


@pytest.fixture
def store(tmp_path):
    return TripStore(tmp_path / "scout.db")
