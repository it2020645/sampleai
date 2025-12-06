from database import engine
from sqlalchemy import text

def check_plan_column():
    with engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='plan_type'"))
            if result.fetchone():
                print("VERIFICATION: Column 'plan_type' EXISTS.")
            else:
                print("VERIFICATION: Column 'plan_type' DOES NOT EXIST.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    check_plan_column()
