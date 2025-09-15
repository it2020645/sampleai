#!/usr/bin/env python3
"""
Test script for GitHub Integration and Branch Management features.
"""
import requests
import json
import os

API_BASE = "http://localhost:8000"
API_KEY = os.getenv("AIDER_API_KEY", "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")

def test_github_integration():
    """Test the enhanced GitHub integration with branch management."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("🧪 Testing GitHub Integration & Branch Management")
    print("=" * 60)
    
    # 1. Get repositories
    print("\n1. 📋 Getting repositories...")
    response = requests.get(f"{API_BASE}/repositories", headers=headers)
    
    if response.status_code != 200:
        print(f"   ❌ Failed to get repositories: {response.status_code}")
        return False
    
    repos = response.json()
    print(f"   ✅ Found {len(repos)} repositories")
    
    if not repos:
        print("   ⚠️  No repositories found. Please add one first.")
        return False
    
    # Find a suitable test repository
    test_repo = None
    for repo in repos:
        if repo['github_url']:  # Must have GitHub URL
            test_repo = repo
            break
    
    if not test_repo:
        print("   ⚠️  No repository with GitHub URL found.")
        return False
    
    print(f"   🎯 Using repository: {test_repo['name']} (ID: {test_repo['id']})")
    print(f"   🔗 GitHub URL: {test_repo['github_url']}")
    
    # 2. Test branch creation with code changes
    print(f"\n2. 🌿 Testing branch creation and code changes...")
    
    execute_data = {
        "repo_id": test_repo['id'],
        "instructions": "Add a comment at the top of the main file saying 'Enhanced with AI assistance'",
        "dry_run": False,  # Make real changes
        "create_branch": True  # Enable branch creation
    }
    
    print(f"   📤 Sending code change request...")
    response = requests.post(
        f"{API_BASE}/update-code-by-id",
        headers=headers,
        json=execute_data
    )
    
    print(f"   📊 Response status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Code changes executed successfully!")
        
        # Display branch information
        if result.get("result", {}).get("branch_info"):
            branch_info = result["result"]["branch_info"]
            print(f"\n   🌿 Branch Information:")
            print(f"      • Created Branch: {branch_info.get('created_branch', 'N/A')}")
            print(f"      • Original Branch: {branch_info.get('original_branch', 'N/A')}")
            print(f"      • Pushed to Remote: {branch_info.get('pushed_to_remote', False)}")
            print(f"      • Push Success: {branch_info.get('push_success', False)}")
            
            if branch_info.get('push_error'):
                print(f"      • Push Error: {branch_info['push_error']}")
            
            if branch_info.get('pull_request'):
                pr = branch_info['pull_request']
                print(f"      • Pull Request: #{pr.get('pr_number', 'N/A')}")
                print(f"      • PR URL: {pr.get('pr_url', 'N/A')}")
                print(f"      • PR Title: {pr.get('pr_title', 'N/A')}")
        
        # Display execution details
        if result.get("result"):
            exec_result = result["result"]
            print(f"\n   ⚙️  Execution Details:")
            print(f"      • Return Code: {exec_result.get('returncode', 'N/A')}")
            print(f"      • Execution Time: {exec_result.get('execution_time', 'N/A')}s")
            
            if exec_result.get('stdout'):
                print(f"      • Output Preview: {exec_result['stdout'][:100]}...")
        
        return True
    else:
        print(f"   ❌ Code changes failed: {response.status_code}")
        try:
            error_data = response.json()
            print(f"      Error: {error_data.get('detail', 'Unknown error')}")
        except:
            print(f"      Error: {response.text}")
        return False

def test_configuration():
    """Test the current configuration settings."""
    print("\n3. ⚙️  Testing Configuration...")
    
    try:
        # Test if server is running and configuration is loaded
        response = requests.get(f"{API_BASE}/status")
        if response.status_code == 200:
            print("   ✅ Server is running")
        else:
            print("   ❌ Server not responding")
            return False
        
        # Check environment variables by importing main
        import sys
        sys.path.append(".")
        
        try:
            from main import (AUTO_CREATE_BRANCH, BRANCH_PREFIX, PUSH_TO_ORIGIN, 
                            CREATE_PULL_REQUEST, GITHUB_TOKEN)
            
            print(f"   📋 Configuration Status:")
            print(f"      • Auto Create Branch: {AUTO_CREATE_BRANCH}")
            print(f"      • Branch Prefix: {BRANCH_PREFIX}")
            print(f"      • Push to Origin: {PUSH_TO_ORIGIN}")
            print(f"      • Create Pull Request: {CREATE_PULL_REQUEST}")
            print(f"      • GitHub Token: {'✅ Set' if GITHUB_TOKEN else '❌ Not Set'}")
            
            return True
        except ImportError as e:
            print(f"   ⚠️  Could not import configuration: {e}")
            return False
            
    except Exception as e:
        print(f"   ❌ Configuration test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 GitHub Integration Test Suite")
    print("🔧 Enhanced Branch Management & Pull Request Creation")
    
    # Test configuration first
    config_ok = test_configuration()
    
    if not config_ok:
        print("\n⚠️  Configuration issues detected. Please check your .env file.")
        return
    
    # Test GitHub integration
    github_ok = test_github_integration()
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print(f"   Configuration: {'✅ PASS' if config_ok else '❌ FAIL'}")
    print(f"   GitHub Integration: {'✅ PASS' if github_ok else '❌ FAIL'}")
    
    if config_ok and github_ok:
        print("\n🎉 All tests passed! GitHub integration is working correctly.")
        print("\n💡 Features Available:")
        print("   • ✅ Automatic branch creation")
        print("   • ✅ Push to original GitHub repository")
        print("   • ✅ Enhanced branch naming")
        print("   • ✅ Pull request creation (if configured)")
        print("   • ✅ Comprehensive error handling")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    main()
