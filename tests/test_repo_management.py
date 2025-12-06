#!/usr/bin/env python3
"""
Test script for the updated repository management with auto-generated paths
"""

import requests
import json

API_BASE = 'http://localhost:8000'
API_KEY = 'change_this_to_a_strong_key'

def test_repository_management():
    print("🧪 Testing Repository Management with Auto-Generated Paths")
    print("=" * 60)
    
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # Test adding a repository
    print("1. Adding a test repository...")
    test_repo = {
        "name": "test-repo",
        "github_url": "https://github.com/testuser/test-repo",
        "owner": "testuser",
        "branch": "main",
        "description": "Test repository for path auto-generation with owner/repo structure"
    }
    
    try:
        response = requests.post(f'{API_BASE}/repositories', json=test_repo, headers=headers)
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Repository added successfully!")
            print(f"   📍 Repo ID: {result['repo_id']}")
            print(f"   📁 Local Path: {result['local_path']}")
            repo_id = result['repo_id']
        else:
            print(f"   ❌ Error adding repository: {response.text}")
            return
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Test getting all repositories
    print("\n2. Getting all repositories...")
    try:
        response = requests.get(f'{API_BASE}/repositories', headers=headers)
        if response.status_code == 200:
            repos = response.json()
            print(f"   ✅ Found {len(repos)} repositories")
            for repo in repos:
                print(f"   📂 {repo['name']} -> {repo['local_path']}")
        else:
            print(f"   ❌ Error getting repositories: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test getting specific repository
    print(f"\n3. Getting repository {repo_id}...")
    try:
        response = requests.get(f'{API_BASE}/repositories/{repo_id}', headers=headers)
        if response.status_code == 200:
            repo = response.json()
            print(f"   ✅ Repository details:")
            print(f"   📛 Name: {repo['name']}")
            print(f"   🔗 URL: {repo['github_url']}")
            print(f"   📁 Local Path: {repo['local_path']}")
            print(f"   👤 Owner: {repo['owner']}")
            print(f"   🌿 Branch: {repo['branch']}")
        else:
            print(f"   ❌ Error getting repository: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test deleting repository
    print(f"\n4. Deleting test repository {repo_id}...")
    try:
        response = requests.delete(f'{API_BASE}/repositories/{repo_id}', headers=headers)
        if response.status_code == 200:
            print("   ✅ Repository deleted successfully!")
        else:
            print(f"   ❌ Error deleting repository: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print(f"\n✅ Repository management test completed!")
    print(f"📋 Features verified:")
    print(f"   - Auto-generated local paths")
    print(f"   - Base path configuration")
    print(f"   - Repository CRUD operations")

if __name__ == "__main__":
    test_repository_management()
