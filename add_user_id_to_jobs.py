import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not set")
    exit(1)

engine = create_engine(DATABASE_URL)

def add_column():
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE jobs ADD COLUMN user_id INTEGER REFERENCES users(id)"))
        conn.commit()
        print("Added user_id column to jobs table")

if __name__ == "__main__":
    try:
        add_column()
    except Exception as e:
        print(f"Error: {e}")
