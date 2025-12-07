"""
Cleanup script for PostgreSQL database - removes repositories and vulnerabilities
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

def cleanup_database():
    """Clean up repositories and vulnerabilities from PostgreSQL database"""

    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        print("   Make sure .env file exists with DATABASE_URL configured")
        return False

    print(f"📁 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Unknown'}")

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Show current counts
            print("\n=== Current Database State ===")

            # Check if tables exist and get counts
            tables_to_check = [
                'repositories',
                'vulnerabilities',
                'jobs',
                'aider_execution_logs',
                'request_logs',
                'api_metric_logs'
            ]

            table_counts = {}
            for table in tables_to_check:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    table_counts[table] = count
                    print(f"  {table}: {count} records")
                except Exception as e:
                    print(f"  {table}: Table not found or error: {str(e)[:50]}")

            # Check what we can delete
            if 'vulnerabilities' not in table_counts and 'repositories' not in table_counts:
                print("\n⚠️  No repositories or vulnerabilities tables found")
                return False

            # Plan cleanup
            print("\n=== Cleanup Plan ===")
            print("The following will be deleted:")

            if table_counts.get('vulnerabilities', 0) > 0:
                print(f"  - {table_counts['vulnerabilities']} vulnerabilities")
            if table_counts.get('jobs', 0) > 0:
                print(f"  - {table_counts['jobs']} jobs")
            if table_counts.get('repositories', 0) > 0:
                print(f"  - {table_counts['repositories']} repositories")

            print("\nNote: Users, request logs, API metrics, and bug reports will be preserved.")

            # Ask for confirmation
            confirm = input("\n⚠️  Proceed with cleanup? (yes/no): ").strip().lower()

            if confirm != 'yes':
                print("❌ Cleanup cancelled.")
                return False

            # Perform cleanup in transaction
            print("\n=== Starting Cleanup ===")

            try:
                # 1. Delete vulnerabilities (references repositories)
                if 'vulnerabilities' in table_counts:
                    result = conn.execute(text("DELETE FROM vulnerabilities"))
                    print(f"✓ Deleted {result.rowcount} vulnerabilities")

                # 2. Delete jobs (references repositories)
                if 'jobs' in table_counts:
                    result = conn.execute(text("DELETE FROM jobs"))
                    print(f"✓ Deleted {result.rowcount} jobs")

                # 3. Delete related logs
                if 'aider_execution_logs' in table_counts:
                    result = conn.execute(text("DELETE FROM aider_execution_logs WHERE repo_id IS NOT NULL"))
                    print(f"✓ Deleted {result.rowcount} aider execution logs")

                if 'request_logs' in table_counts:
                    result = conn.execute(text("DELETE FROM request_logs WHERE repo_id IS NOT NULL"))
                    print(f"✓ Deleted {result.rowcount} request logs")

                if 'api_metric_logs' in table_counts:
                    result = conn.execute(text("DELETE FROM api_metric_logs WHERE repo_id IS NOT NULL"))
                    print(f"✓ Deleted {result.rowcount} API metric logs")

                # 4. Finally delete repositories
                if 'repositories' in table_counts:
                    result = conn.execute(text("DELETE FROM repositories"))
                    print(f"✓ Deleted {result.rowcount} repositories")

                # Commit transaction
                conn.commit()
                print("\n✅ Transaction committed successfully")

            except Exception as e:
                conn.rollback()
                print(f"\n❌ Error during cleanup, rolling back: {e}")
                return False

            # Show final counts
            print("\n=== Final Database State ===")
            for table in tables_to_check:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    print(f"  {table}: {count} records")
                except:
                    pass

            print("\n✅ Cleanup completed successfully!")
            return True

    except Exception as e:
        print(f"❌ Database connection error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    cleanup_database()
