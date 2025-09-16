#!/usr/bin/env python3
"""
Test script to verify the cloning functionality works correctly.
"""
import requests
import json

API_BASE = "http://localhost:8000"
API_KEY = "change_this_to_a_strong_key"

def test_repository_clone():
    """Test cloning a repository that doesn't exist locally."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("🔍 Testing repository cloning functionality...")
    
    # First, get the list of repositories
    print("\n1. Getting list of repositories...")
    response = requests.get(f"{API_BASE}/repositories", headers=headers)
    
    if response.status_code == 200:
        repos = response.json()
        print(f"   Found {len(repos)} repositories")
        
        if repos:
            # Find the romualdez repository
            target_repo = None
            for repo in repos:
                if repo['name'] == 'romualdez' and repo['owner'] == 'it2020645':
                    target_repo = repo
                    break
            
            if target_repo:
                print(f"\n2. Found target repository: {target_repo['name']} (ID: {target_repo['id']})")
                print(f"   GitHub URL: {target_repo['github_url']}")
                print(f"   Expected path: C:/Users/batal/OneDrive/Documents/GitHub/ai/{target_repo['owner']}/{target_repo['name']}")
                
                # Try to clone the repository
                print(f"\n3. Testing clone functionality...")
                clone_response = requests.post(
                    f"{API_BASE}/repositories/{target_repo['id']}/clone",
                    headers=headers
                )
                
                if clone_response.status_code == 200:
                    result = clone_response.json()
                    print(f"   Clone status: {result['status']}")
                    print(f"   Message: {result['message']}")
                    if 'path' in result:
                        print(f"   Path: {result['path']}")
                    return True
                else:
                    print(f"   ❌ Clone failed with status {clone_response.status_code}")
                    print(f"   Response: {clone_response.text}")
                    return False
            else:
                print("   ⚠️  Target repository 'it2020645/romualdez' not found in database")
                return False
        else:
            print("   ⚠️  No repositories found in database")
            return False
    else:
        print(f"   ❌ Failed to get repositories: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def test_code_execution():
    """Test code execution that should trigger auto-cloning."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("\n🚀 Testing code execution with auto-cloning...")
    
    # Get repositories
    response = requests.get(f"{API_BASE}/repositories", headers=headers)
    if response.status_code == 200:
        repos = response.json()
        target_repo = None
        for repo in repos:
            if repo['name'] == 'romualdez' and repo['owner'] == 'it2020645':
                target_repo = repo
                break
        
        if target_repo:
            print(f"   Using repository: {target_repo['name']} (ID: {target_repo['id']})")
            
            # Try to execute code changes
            execute_data = {
                "repo_id": target_repo['id'],
                "instructions": "Add a comment to the main file saying 'Hello from AI assistant'",
                "dry_run": True
            }
            
            execute_response = requests.post(
                f"{API_BASE}/update-code-by-id",
                headers=headers,
                json=execute_data
            )
            
            print(f"   Execute status: {execute_response.status_code}")
            result = execute_response.json()
            print(f"   Response: {json.dumps(result, indent=2)}")
            
            return execute_response.status_code == 200
        else:
            print("   ⚠️  Target repository not found")
            return False
    else:
        print(f"   ❌ Failed to get repositories: {response.status_code}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Enhanced Repository Management System")
    print("=" * 50)
    
    # Test cloning
    clone_success = test_repository_clone()
    
    # Test execution with auto-cloning
    execute_success = test_code_execution()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"   Clone functionality: {'✅ PASS' if clone_success else '❌ FAIL'}")
    print(f"   Code execution: {'✅ PASS' if execute_success else '❌ FAIL'}")
    
    if clone_success and execute_success:
        print("\n🎉 All tests passed! The enhanced system is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
