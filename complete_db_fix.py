import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def complete_database_fix():
    """Add ALL missing columns to match your models exactly."""
    
    db_url = os.getenv("DATABASE_URL")
    
    try:
        # Connect to PostgreSQL with autocommit
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("🔄 Complete database schema fix...")
        
        # === REPOSITORIES TABLE ===
        print("\n📋 Fixing repositories table...")
        
        # Check current columns
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'repositories'
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"Current columns: {existing_columns}")
        
        # Add missing columns to repositories
        columns_to_add = [
            ("user_id", "INTEGER"),
            ("is_public", "BOOLEAN DEFAULT FALSE"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE repositories ADD COLUMN {column_name} {column_type}")
                    print(f"✅ Added {column_name} to repositories")
                except Exception as e:
                    print(f"❌ Error adding {column_name}: {e}")
            else:
                print(f"✅ repositories.{column_name} already exists")
        
        # === REQUEST_LOGS TABLE ===
        print("\n📋 Fixing request_logs table...")
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'request_logs'
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"Current columns: {existing_columns}")
        
        # Add missing columns to request_logs
        request_log_columns = [
            ("user_id", "INTEGER"),
            ("execution_time", "FLOAT"),
            ("result_data", "TEXT"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_type in request_log_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE request_logs ADD COLUMN {column_name} {column_type}")
                    print(f"✅ Added {column_name} to request_logs")
                except Exception as e:
                    print(f"❌ Error adding {column_name}: {e}")
            else:
                print(f"✅ request_logs.{column_name} already exists")
        
        # === AIDER_EXECUTION_LOGS TABLE ===
        print("\n📋 Fixing aider_execution_logs table...")
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'aider_execution_logs'
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"Current columns: {existing_columns}")
        
        # Add missing columns to aider_execution_logs
        aider_log_columns = [
            ("user_id", "INTEGER"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_type in aider_log_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE aider_execution_logs ADD COLUMN {column_name} {column_type}")
                    print(f"✅ Added {column_name} to aider_execution_logs")
                except Exception as e:
                    print(f"❌ Error adding {column_name}: {e}")
            else:
                print(f"✅ aider_execution_logs.{column_name} already exists")
        
        # === CREATE USERS TABLE IF NOT EXISTS ===
        print("\n👥 Creating users table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                google_id VARCHAR UNIQUE,
                email VARCHAR UNIQUE,
                name VARCHAR,
                picture_url VARCHAR,
                is_active BOOLEAN DEFAULT TRUE,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)
        print("✅ Users table created/verified")
        
        # === CREATE API_METRIC_LOGS TABLE IF NOT EXISTS ===
        print("\n📊 Creating api_metric_logs table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_metric_logs (
                id SERIAL PRIMARY KEY,
                endpoint VARCHAR,
                repo_id INTEGER,
                user_id INTEGER,
                metric_name VARCHAR,
                metric_value FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ api_metric_logs table created/verified")
        
        # === FINAL VERIFICATION ===
        print("\n🔍 Final verification...")
        
        tables_to_verify = ['repositories', 'request_logs', 'aider_execution_logs', 'users', 'api_metric_logs']
        
        for table in tables_to_verify:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            result = cursor.fetchone()
            count = result[0] if result else 0
            print(f"✅ {table}: {count} records")
            
            # Show column structure
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s 
                ORDER BY ordinal_position
            """, (table,))
            
            columns = cursor.fetchall()
            column_list = [f"{col[0]}({col[1]})" for col in columns]
            print(f"   Columns: {', '.join(column_list)}")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Complete database fix successful!")
        return True
        
    except Exception as e:
        print(f"❌ Complete database fix failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    complete_database_fix()