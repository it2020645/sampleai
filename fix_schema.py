import os
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"Connecting to database...")

try:
    engine = create_engine(DATABASE_URL)
    
    # Check current columns
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('users')]
    print(f"Current columns in 'users' table: {columns}")
    
    if 'updated_at' not in columns:
        print("Column 'updated_at' is missing. Adding it now...")
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.commit()
        print("✅ Successfully added 'updated_at' column.")
    else:
        print("✅ Column 'updated_at' already exists.")
        
except Exception as e:
    print(f"❌ Error: {e}")
