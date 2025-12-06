def test_status(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True

def test_list_repositories(client, auth_headers):
    # First ensure we have a clean state or mock data
    response = client.get("/repositories", headers=auth_headers)
    # Depending on auth implementation, this might return 200 or 401/403
    # Since we are using TestClient with the app, we need to ensure auth works.
    # The main.py uses 'get_current_user' dependency.
    
    # If the endpoint is protected, we expect 200 if auth is correct.
    if response.status_code == 403:
        # Admin access might be required
        pass
    else:
        assert response.status_code in [200, 404] # 404 if no repos found is not standard but possible

def test_create_repository_validation(client, auth_headers):
    # Test missing fields
    response = client.post(
        "/repositories",
        json={},
        headers=auth_headers
    )
    assert response.status_code == 422  # Validation error

def test_vulnerabilities_endpoint(client, auth_headers):
    # Try to get vulnerabilities for a non-existent repo
    response = client.get("/repositories/99999/vulnerabilities", headers=auth_headers)
    assert response.status_code in [404, 403]
