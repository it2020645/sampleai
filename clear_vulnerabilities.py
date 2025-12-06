from database import SessionLocal
from models import Vulnerability
import sys

def clear_vulnerabilities():
    db = SessionLocal()
    try:
        count = db.query(Vulnerability).delete()
        db.commit()
        print(f"Successfully deleted {count} vulnerabilities.")
    except Exception as e:
        print(f"Error clearing vulnerabilities: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    clear_vulnerabilities()
