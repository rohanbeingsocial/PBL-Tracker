"""Tests run against a database built with scripts/setup_db.py and scripts/load_data.py.
Every test works inside one transaction that is rolled back at the end, so the
database is left exactly as it was."""
import psycopg
import pytest
from psycopg.rows import dict_row

from finder.config import require


def _connect(url_name: str) -> psycopg.Connection:
    return psycopg.connect(require(url_name), row_factory=dict_row, connect_timeout=10)


@pytest.fixture
def db():
    """Owner connection (the one the scripts use)."""
    with _connect("ADMIN_DATABASE_URL") as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def app_db():
    """The pbl_app login the web app uses."""
    with _connect("DATABASE_URL") as conn:
        yield conn
        conn.rollback()
