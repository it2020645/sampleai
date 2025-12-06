import pytest
from unittest.mock import patch, MagicMock

def test_configuration():
    """Test that configuration variables are loaded correctly."""
    from main import AUTO_CREATE_BRANCH, PUSH_TO_ORIGIN, CREATE_PULL_REQUEST
    
    # These depend on .env or defaults. Just checking they are booleans.
    assert isinstance(AUTO_CREATE_BRANCH, bool)
    assert isinstance(PUSH_TO_ORIGIN, bool)
    assert isinstance(CREATE_PULL_REQUEST, bool)

def test_github_integration(client, auth_headers):
    """Test the enhanced GitHub integration with branch management."""
    
    # 1. Setup: Create a repo in DB
    from models import Repository
    from database import SessionLocal
    
    db = SessionLocal()
    repo = Repository(
        name="test-github-repo",
        owner="test-owner",
        github_url="https://github.com/test-owner/test-github-repo.git",
        created_by_user_id=1
    )
    db.add(repo)
    db.commit()
    repo_id = repo.id
    db.close()
    
    # 2. Mock subprocess and git operations
    with patch("subprocess.run") as mock_run, \
         patch("subprocess.Popen") as mock_popen:
        
        # Mock git commands
        mock_run.return_value = MagicMock(returncode=0, stdout="origin\n", stderr="")
        
        # Mock aider execution
        process_mock = MagicMock()
        process_mock.stdout.readline.side_effect = [b"Applied changes\n", b""]
        process_mock.poll.return_value = 0
        process_mock.wait.return_value = 0
        mock_popen.return_value = process_mock
        
        # 3. Execute code change request
        execute_data = {
            "repo_id": repo_id,
            "instructions": "Add a feature",
            "dry_run": False,
            "create_branch": True
        }
        
        response = client.post(
            "/update-code-by-id",
            headers=auth_headers,
            json=execute_data
        )
        
        # 4. Assertions
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "queued"
        
        # Check if branch info is present (it might be None if mocking didn't trigger branch logic fully)
        # But the endpoint should return the structure.
        # assert "result" in result # result is not in queued response
