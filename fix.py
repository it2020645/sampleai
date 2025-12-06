import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def fix_database():
    """Add missing user_id columns using direct PostgreSQL connection."""
    
    db_url = os.getenv("DATABASE_URL")
    
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(db_url)
        conn.autocommit = True  # Important: Enable autocommit to avoid transaction issues
        cursor = conn.cursor()
        
        print("🔄 Fixing database schema with autocommit...")
        
        # List of tables that need user_id column
        tables = ['repositories', 'request_logs', 'aider_execution_logs', 'api_metric_logs']
        
        for table in tables:
            print(f"\n📋 Working on table: {table}")
            
            # Check if user_id column exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'user_id'
            """, (table,))
            
            if cursor.fetchone():
                print(f"✅ {table}.user_id already exists")
            else:
                print(f"➕ Adding user_id column to {table}")
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
                    print(f"✅ Added user_id column to {table}")
                except Exception as e:
                    print(f"❌ Error adding column to {table}: {e}")
        
        # Verify all columns were added
        print("\n🔍 Verifying columns...")
        for table in tables:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'user_id'
            """, (table,))
            
            if cursor.fetchone():
                print(f"✅ {table}.user_id exists")
            else:
                print(f"❌ {table}.user_id missing")
        
        # Show all columns for repositories table
        print("\n📊 Current repositories table structure:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'repositories'
            ORDER BY ordinal_position
        """)
        
        for row in cursor.fetchall():
            print(f"   {row[0]} ({row[1]}) - Nullable: {row[2]}")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Database fix completed!")
        return True
        
    except Exception as e:
        print(f"❌ Database fix failed: {e}")
        return False

if __name__ == "__main__":
    fix_database()