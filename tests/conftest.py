import pytest
from pipeline_lock.db import get_connection

@pytest.fixture
def conn():
    """Provide a fresh in-memory database connection for each test."""
    conn = get_connection(":memory:")
    yield conn
    conn.close()