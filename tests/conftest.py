import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base, RDBMS
import main # Import main to patch db if needed

from sqlalchemy.pool import StaticPool

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def test_db():
    """
    Creates a fresh database for each test.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def mock_session_local():
    """
    Patches database.SessionLocal to use the test database.
    """
    with patch("database.SessionLocal", side_effect=TestingSessionLocal) as mock:
        yield mock

@pytest.fixture(scope="function")
def client(test_db, mock_session_local):
    """
    Test client that uses the test database.
    """
    # Override get_current_user dependency
    def mock_get_current_user():
        return {
            "user_id": "test_google_id",
            "email": "test@example.com",
            "name": "Test User",
            "picture": ""
        }

    main.app.dependency_overrides[main.get_current_user] = mock_get_current_user
    
    # Create a user in the DB for foreign key constraints
    db = TestingSessionLocal()
    from models import User
    # Check if user exists first (though test_db should be fresh)
    if not db.query(User).filter_by(google_id="test_google_id").first():
        user = User(
            google_id="test_google_id",
            email="test@example.com",
            name="Test User",
            plan_type="pro"
        )
        db.add(user)
        db.commit()
    db.close()

    with TestClient(main.app) as c:
        yield c
    
    main.app.dependency_overrides.clear()

@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer mock_token"}
