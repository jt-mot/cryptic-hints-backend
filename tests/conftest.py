"""Shared test fixtures. Patches the DB before production_app is imported."""
import sys
import json
from unittest.mock import patch, MagicMock

import pytest


# Patch psycopg2.connect at the module level BEFORE production_app is imported,
# since it runs a DB check on import.
_mock_conn = MagicMock()
_mock_cursor = MagicMock()
_mock_conn.cursor.return_value = _mock_cursor
_mock_conn.execute.return_value = None

_patcher = patch('psycopg2.connect', return_value=_mock_conn)
_patcher.start()

# Now it's safe to import
from production_app import app as _flask_app


@pytest.fixture
def app():
    _flask_app.config['TESTING'] = True
    _flask_app.config['SECRET_KEY'] = 'test-secret'
    yield _flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(client):
    """Client with active admin session."""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 'admin'
    return client


@pytest.fixture(autouse=True)
def mock_db():
    """Provide a fresh mock cursor for each test."""
    _mock_cursor.reset_mock()
    _mock_conn.reset_mock()
    _mock_conn.cursor.return_value = _mock_cursor
    _mock_conn.execute.return_value = None

    with patch('production_app.get_db', return_value=_mock_conn):
        yield _mock_cursor
