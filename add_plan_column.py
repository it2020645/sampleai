from database import engine
from sqlalchemy import text

def add_plan_column():
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='plan_type'"))
            if result.fetchone():
                print("Column 'plan_type' already exists.")
                return

            # Add column
            print("Adding 'plan_type' column to users table...")
            conn.execute(text("ALTER TABLE users ADD COLUMN plan_type VARCHAR DEFAULT 'free'"))
            conn.commit()
            print("Successfully added 'plan_type' column.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    add_plan_column()
