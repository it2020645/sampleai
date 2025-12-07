"""
Comprehensive cleanup script for repositories and vulnerabilities
Works with direct SQLite connection since database.py is not available
"""
import sqlite3
import sys
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def find_database():
    """Find the actual database file being used"""
    possible_dbs = [
        "test.db",
        "test_aider.db",
        "sampleai.db",
        "app.db"
    ]

    for db in possible_dbs:
        db_path = Path(db)
        if db_path.exists():
            # Check if it has the tables we need
            try:
                conn = sqlite3.connect(db)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()

                if 'repositories' in tables or 'vulnerabilities' in tables:
                    return str(db_path)
            except:
                continue

    return None

def cleanup_database(db_path: str):
    """Clean up repositories and vulnerabilities from the database"""

    if not Path(db_path).exists():
        print(f"❌ Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get list of all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        print(f"\n📁 Database: {db_path}")
        print(f"📊 Tables found: {', '.join(tables)}")

        # Show current counts for all tables
        print("\n=== Current Database State ===")

        table_counts = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            table_counts[table] = count
            print(f"  {table}: {count} records")

        # Check if we have the tables we want to clean
        has_repos = 'repositories' in tables
        has_vulns = 'vulnerabilities' in tables
        has_jobs = 'jobs' in tables

        if not has_repos and not has_vulns:
            print("\n⚠️  No 'repositories' or 'vulnerabilities' tables found.")
            print("   Database appears to be empty or using different schema.")
            conn.close()
            return False

        # Plan cleanup
        print("\n=== Cleanup Plan ===")
        to_delete = []

        if has_vulns:
            to_delete.append(f"  - {table_counts['vulnerabilities']} vulnerabilities")
        if has_jobs:
            to_delete.append(f"  - {table_counts['jobs']} jobs")
        if has_repos:
            to_delete.append(f"  - {table_counts['repositories']} repositories")

        if to_delete:
            print("The following will be deleted:")
            for item in to_delete:
                print(item)
        else:
            print("  Nothing to delete.")
            conn.close()
            return True

        # Ask for confirmation
        confirm = input("\n⚠️  Proceed with cleanup? (yes/no): ").strip().lower()

        if confirm != 'yes':
            print("❌ Cleanup cancelled.")
            conn.close()
            return False

        # Perform cleanup in correct order (respecting foreign keys)
        print("\n=== Starting Cleanup ===")

        deleted_counts = {}

        # 1. Delete vulnerabilities first (references repositories)
        if has_vulns:
            cursor.execute("DELETE FROM vulnerabilities")
            deleted_counts['vulnerabilities'] = table_counts['vulnerabilities']
            print(f"✓ Deleted {deleted_counts['vulnerabilities']} vulnerabilities")

        # 2. Delete jobs (references repositories)
        if has_jobs:
            cursor.execute("DELETE FROM jobs")
            deleted_counts['jobs'] = table_counts['jobs']
            print(f"✓ Deleted {deleted_counts['jobs']} jobs")

        # 3. Delete related logs if they exist
        if 'aider_execution_logs' in tables:
            cursor.execute("DELETE FROM aider_execution_logs WHERE repo_id IS NOT NULL")
            print(f"✓ Deleted related aider execution logs")

        if 'request_logs' in tables:
            cursor.execute("DELETE FROM request_logs WHERE repo_id IS NOT NULL")
            print(f"✓ Deleted related request logs")

        if 'api_metric_logs' in tables:
            cursor.execute("DELETE FROM api_metric_logs WHERE repo_id IS NOT NULL")
            print(f"✓ Deleted related API metric logs")

        # 4. Finally delete repositories
        if has_repos:
            cursor.execute("DELETE FROM repositories")
            deleted_counts['repositories'] = table_counts['repositories']
            print(f"✓ Deleted {deleted_counts['repositories']} repositories")

        # Commit changes
        conn.commit()

        # Show final counts
        print("\n=== Final Database State ===")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} records")

        print("\n✅ Cleanup completed successfully!")

        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Try to find database automatically or accept as argument
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        print("🔍 Searching for database...")
        db_path = find_database()

        if db_path is None:
            print("❌ No database found with repositories/vulnerabilities tables.")
            print("   Available .db files:")
            for db_file in Path('.').glob('*.db'):
                print(f"     - {db_file}")
            print("\nUsage: python cleanup_repos_and_vulns.py [database_path]")
            sys.exit(1)

    cleanup_database(db_path)
