import sys
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import RDBMS, engine

def test_api_health(client):
    """Test the API health check endpoint."""
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "database" in data
    assert "message" in data

def test_database_connection(mock_session_local):
    """Test that the database is accessible."""
    try:
        # We use the mocked session local to get a session
        from database import SessionLocal
        session = SessionLocal()
        # Execute a simple query
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
        session.close()
    except Exception as e:
        pytest.fail(f"Database connection failed: {e}")

def test_environment_variables():
    """Ensure critical environment variables are set."""
    required_vars = ["OPENAI_API_KEY", "DATABASE_URL"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        pytest.fail(f"Missing environment variables: {', '.join(missing)}")
