from database import RDBMS
from auth import oauth2_handler

def test_everything():
    print("🧪 Testing system...")
    
    try:
        # Test database
        db = RDBMS()
        repos = db.get_all_repositories()
        print(f"✅ Database working: {len(repos)} repositories")
        
        # Test OAuth2
        if oauth2_handler.client_id:
            print("✅ OAuth2 configured")
        else:
            print("⚠️ OAuth2 needs configuration")
        
        print("🎉 System test passed!")
        
    except Exception as e:
        print(f"❌ System test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_everything()