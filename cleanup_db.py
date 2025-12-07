"""
Database cleanup script for repositories and vulnerabilities
"""
import sqlite3
import sys
from pathlib import Path

def cleanup_database(db_path: str):
    """Clean up repositories and vulnerabilities from the database"""

    if not Path(db_path).exists():
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Show current counts
        print("\n=== Current Database State ===")
        cursor.execute("SELECT COUNT(*) FROM repositories")
        repo_count = cursor.fetchone()[0]
        print(f"Repositories: {repo_count}")

        cursor.execute("SELECT COUNT(*) FROM vulnerabilities")
        vuln_count = cursor.fetchone()[0]
        print(f"Vulnerabilities: {vuln_count}")

        # Also check related tables
        cursor.execute("SELECT COUNT(*) FROM jobs")
        job_count = cursor.fetchone()[0]
        print(f"Jobs: {job_count}")

        cursor.execute("SELECT COUNT(*) FROM aider_execution_logs")
        aider_log_count = cursor.fetchone()[0]
        print(f"Aider Execution Logs: {aider_log_count}")

        # Ask for confirmation
        print("\n=== Cleanup Plan ===")
        print("The following will be deleted:")
        print(f"  - {vuln_count} vulnerabilities")
        print(f"  - {job_count} jobs (related to repositories)")
        print(f"  - {aider_log_count} aider execution logs")
        print(f"  - {repo_count} repositories")
        print("\nNote: Users, request logs, API metrics, and bug reports will be preserved.")

        confirm = input("\nProceed with cleanup? (yes/no): ").strip().lower()

        if confirm != 'yes':
            print("Cleanup cancelled.")
            conn.close()
            return False

        # Perform cleanup in correct order (respecting foreign keys)
        print("\n=== Starting Cleanup ===")

        # 1. Delete vulnerabilities (references repositories)
        cursor.execute("DELETE FROM vulnerabilities")
        print(f"✓ Deleted {vuln_count} vulnerabilities")

        # 2. Delete jobs (references repositories)
        cursor.execute("DELETE FROM jobs")
        print(f"✓ Deleted {job_count} jobs")

        # 3. Delete aider execution logs
        cursor.execute("DELETE FROM aider_execution_logs WHERE repo_id IS NOT NULL")
        print(f"✓ Deleted aider execution logs")

        # 4. Delete repositories
        cursor.execute("DELETE FROM repositories")
        print(f"✓ Deleted {repo_count} repositories")

        # Commit changes
        conn.commit()

        # Show final counts
        print("\n=== Final Database State ===")
        cursor.execute("SELECT COUNT(*) FROM repositories")
        print(f"Repositories: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM vulnerabilities")
        print(f"Vulnerabilities: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM jobs")
        print(f"Jobs: {cursor.fetchone()[0]}")

        print("\n✓ Cleanup completed successfully!")

        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # Default to test.db, or accept database path as argument
    db_path = sys.argv[1] if len(sys.argv) > 1 else "test.db"

    print(f"Database: {db_path}")
    cleanup_database(db_path)
