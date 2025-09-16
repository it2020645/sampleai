#!/usr/bin/env python3
"""
Simple test script for the lightweight database
"""

from database import LightDatabase

def test_database():
    print("🗄️  Testing Lightweight Database")
    print("=" * 50)
    
    # Initialize database
    db = LightDatabase("test_aider.db")
    
    # Test logging a request
    print("1. Logging a test request...")
    request_id = db.log_request(
        endpoint="/update-code",
        repo_path="/test/repo",
        instructions="Add a hello world function",
        dry_run=False,
        status="processing"
    )
    print(f"   Request logged with ID: {request_id}")
    
    # Test logging aider execution
    print("2. Logging an aider execution...")
    exec_id = db.log_aider_execution(
        repo_path="/test/repo",
        instructions="Add a hello world function",
        returncode=0,
        stdout="Files modified: main.py",
        stderr="",
        execution_time=2.5
    )
    print(f"   Execution logged with ID: {exec_id}")
    
    # Test updating request status
    print("3. Updating request status...")
    db.update_request_status(
        request_id=request_id,
        status="completed",
        execution_time=3.2,
        result_data={"status": "success", "files_modified": ["main.py"]}
    )
    print("   Request status updated")
    
    # Test API metrics
    print("4. Logging API metrics...")
    db.log_api_metric(
        endpoint="/update-code",
        method="POST",
        status_code=200,
        response_time=3.2
    )
    print("   API metrics logged")
    
    # Test getting recent requests
    print("5. Getting recent requests...")
    recent = db.get_recent_requests(limit=5)
    print(f"   Found {len(recent)} recent requests")
    
    # Test getting repo history
    print("6. Getting repo history...")
    history = db.get_repo_history("/test/repo", limit=5)
    print(f"   Found {len(history)} executions for /test/repo")
    
    # Test getting stats
    print("7. Getting API stats...")
    stats = db.get_api_stats(hours=24)
    print(f"   Overall stats: {stats['overall']}")
    print(f"   Endpoint stats: {len(stats['by_endpoint'])} endpoints")
    
    print("\n✅ Database test completed successfully!")
    print("📊 Database file created: test_aider.db")

if __name__ == "__main__":
    test_database()
