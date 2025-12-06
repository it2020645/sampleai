import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models import Repository

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Check what's actually in your PostgreSQL database right now
session = SessionLocal()
repositories = session.query(Repository).all()
session.close()

print("Repositories in PostgreSQL database:")
for repo in repositories:
    print(f"ID: {repo.id}, Name: {repo.name}, URL: {repo.github_url}, Owner: {repo.owner}")