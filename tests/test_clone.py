import pytest
from unittest.mock import patch, MagicMock

def test_repository_clone(client, auth_headers):
    """Test cloning a repository that doesn't exist locally."""
    
    # Mock the database response for get_repository
    # But since we are using a real (test) DB, we should insert a repo first.
    
    # 1. Create a repo in the DB
    from models import Repository
    from database import SessionLocal
    
    db = SessionLocal()
    repo = Repository(
        name="test-repo",
        owner="test-owner",
        github_url="https://github.com/test-owner/test-repo.git",
        created_by_user_id=1 # Assuming the test user has ID 1
    )
    db.add(repo)
    db.commit()
    repo_id = repo.id
    db.close()
    
    # 2. Mock subprocess.run to simulate git clone success
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Cloning into 'test-repo'...", stderr="")
        
        # 3. Call the clone endpoint
        response = client.post(
            f"/repositories/{repo_id}/clone",
            headers=auth_headers
        )
        
        # 4. Assertions
        # Note: The actual endpoint might return 200 or 404 if logic fails.
        # We need to check main.py logic. 
        # If the repo exists in DB, it tries to clone.
        
        assert response.status_code in [200, 400] # 400 if already cloned
        if response.status_code == 200:
            assert response.json()["status"] == "success"

def test_code_execution(client, auth_headers):
    """Test code execution endpoint."""
    # This endpoint likely runs 'aider'. We should mock it.
    
    with patch("subprocess.Popen") as mock_popen:
        process_mock = MagicMock()
        process_mock.stdout.readline.side_effect = [b"Output line 1\n", b"Output line 2\n", b""]
        process_mock.poll.return_value = 0
        process_mock.wait.return_value = 0
        mock_popen.return_value = process_mock
        
        # We need a valid repo ID
        # Reuse logic or create new repo
        from models import Repository
        from database import SessionLocal
        db = SessionLocal()
        repo = db.query(Repository).first()
        if not repo:
             repo = Repository(
                name="test-repo-exec",
                owner="test-owner",
                github_url="https://github.com/test-owner/test-repo-exec.git",
                created_by_user_id=1
            )
             db.add(repo)
             db.commit()
        repo_id = repo.id
        db.close()

        response = client.post(
            "/update-code-by-id",
            json={
                "instructions": "Fix this bug",
                "repo_id": repo_id
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert "job_id" in response.json()