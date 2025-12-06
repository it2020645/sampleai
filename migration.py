import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from dotenv import load_dotenv
from models import Base

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def migrate_database():
    """Add missing columns to existing tables and create new tables."""
    print("🔄 Starting database migration...")

    if not DATABASE_URL:
        print("❌ DATABASE_URL is not set in your environment variables.")
        return False

    engine = create_engine(DATABASE_URL)
    
    try:
        # First, create all missing tables
        print("🆕 Creating any missing tables...")
        Base.metadata.create_all(engine)
        print("✅ Tables created/verified")
        
        # Now add missing columns with separate transactions
        with engine.connect() as conn:
            
            # Add user_id column to repositories table if it doesn't exist
            try:
                conn.execute(text("SELECT user_id FROM repositories LIMIT 1"))
                print("✅ repositories.user_id column exists")
            except (OperationalError, ProgrammingError):
                print("➕ Adding user_id column to repositories table...")
                try:
                    conn.execute(text("ALTER TABLE repositories ADD COLUMN user_id INTEGER"))
                    conn.commit()
                    print("✅ repositories.user_id column added")
                    
                    # Add foreign key constraint in separate transaction
                    conn.execute(text("ALTER TABLE repositories ADD CONSTRAINT fk_repositories_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
                    conn.commit()
                    print("✅ repositories foreign key constraint added")
                except Exception as e:
                    print(f"⚠️  repositories.user_id: {e}")
                    conn.rollback()
            
            # Add user_id column to request_logs table if it doesn't exist
            try:
                conn.execute(text("SELECT user_id FROM request_logs LIMIT 1"))
                print("✅ request_logs.user_id column exists")
            except (OperationalError, ProgrammingError):
                print("➕ Adding user_id column to request_logs table...")
                try:
                    conn.execute(text("ALTER TABLE request_logs ADD COLUMN user_id INTEGER"))
                    conn.commit()
                    print("✅ request_logs.user_id column added")
                    
                    # Add foreign key constraint in separate transaction
                    conn.execute(text("ALTER TABLE request_logs ADD CONSTRAINT fk_request_logs_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
                    conn.commit()
                    print("✅ request_logs foreign key constraint added")
                except Exception as e:
                    print(f"⚠️  request_logs.user_id: {e}")
                    conn.rollback()
            
            # Add user_id column to aider_execution_logs table if it doesn't exist
            try:
                conn.execute(text("SELECT user_id FROM aider_execution_logs LIMIT 1"))
                print("✅ aider_execution_logs.user_id column exists")
            except (OperationalError, ProgrammingError):
                print("➕ Adding user_id column to aider_execution_logs table...")
                try:
                    conn.execute(text("ALTER TABLE aider_execution_logs ADD COLUMN user_id INTEGER"))
                    conn.commit()
                    print("✅ aider_execution_logs.user_id column added")
                    
                    # Add foreign key constraint in separate transaction
                    conn.execute(text("ALTER TABLE aider_execution_logs ADD CONSTRAINT fk_aider_execution_logs_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
                    conn.commit()
                    print("✅ aider_execution_logs foreign key constraint added")
                except Exception as e:
                    print(f"⚠️  aider_execution_logs.user_id: {e}")
                    conn.rollback()
            
            # Add user_id column to api_metric_logs table if it doesn't exist
            try:
                conn.execute(text("SELECT user_id FROM api_metric_logs LIMIT 1"))
                print("✅ api_metric_logs.user_id column exists")
            except (OperationalError, ProgrammingError):
                print("➕ Adding user_id column to api_metric_logs table...")
                try:
                    conn.execute(text("ALTER TABLE api_metric_logs ADD COLUMN user_id INTEGER"))
                    conn.commit()
                    print("✅ api_metric_logs.user_id column added")
                    
                    # Add foreign key constraint in separate transaction
                    conn.execute(text("ALTER TABLE api_metric_logs ADD CONSTRAINT fk_api_metric_logs_user_id FOREIGN KEY (user_id) REFERENCES users(id)"))
                    conn.commit()
                    print("✅ api_metric_logs foreign key constraint added")
                except Exception as e:
                    print(f"⚠️  api_metric_logs.user_id: {e}")
                    conn.rollback()
    
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False
    
    print("🎉 Database migration completed successfully!")
    return True

def verify_migration():
    """Verify that the migration was successful."""
    print("\n🔍 Verifying migration...")
    if not DATABASE_URL:
        print("❌ DATABASE_URL is not set in your environment variables.")
        return False
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # Test each table
            tables_to_check = [
                "users",
                "repositories", 
                "request_logs",
                "aider_execution_logs",
                "api_metric_logs"
            ]
            
            for table in tables_to_check:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    print(f"✅ {table}: {count} records")
                except Exception as e:
                    print(f"❌ {table}: {e}")
            
            # Test user_id columns specifically
            user_id_tables = ["repositories", "request_logs", "aider_execution_logs", "api_metric_logs"]
            for table in user_id_tables:
                try:
                    conn.execute(text(f"SELECT user_id FROM {table} LIMIT 1"))
                    print(f"✅ {table}.user_id column exists")
                except Exception as e:
                    print(f"❌ {table}.user_id: {e}")
                    
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False
    
    print("✅ Migration verification completed!")
    return True

if __name__ == "__main__":
    success = migrate_database()
    if success:
        verify_migration()
        print("\n✅ Your database is now ready for OAuth2!")
        print("Next steps:")
        print("1. Update GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file")
        print("2. Start your app: python main.py")
        print("3. Test OAuth2 at: http://localhost:8000/docs")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")