import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("database")

class LightDatabase:
    """
    A very lightweight SQLite database wrapper for the Aider API server.
    Stores request logs, execution history, and basic metrics.
    """
    
    def __init__(self, db_path: str = "aider_api.db"):
        self.db_path = Path(db_path)
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            # Repositories table for storing GitHub repo info
            conn.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    github_url TEXT NOT NULL UNIQUE,
                    owner TEXT NOT NULL,
                    branch TEXT NOT NULL DEFAULT 'main',
                    github_token TEXT,
                    local_path TEXT,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    repo_id INTEGER,
                    repo_path TEXT,
                    instructions TEXT,
                    dry_run BOOLEAN,
                    status TEXT,
                    execution_time REAL,
                    result_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (repo_id) REFERENCES repositories (id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aider_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_id INTEGER,
                    repo_path TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    returncode INTEGER,
                    stdout TEXT,
                    stderr TEXT,
                    execution_time REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (repo_id) REFERENCES repositories (id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER,
                    response_time REAL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    def log_request(self, endpoint: str, repo_id: Optional[int] = None, repo_path: Optional[str] = None, 
                   instructions: Optional[str] = None, dry_run: bool = False, status: str = "pending", 
                   execution_time: Optional[float] = None, result_data: Optional[dict] = None) -> int:
        """Log an API request."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO request_logs 
                (timestamp, endpoint, repo_id, repo_path, instructions, dry_run, status, execution_time, result_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                endpoint,
                repo_id,
                repo_path,
                instructions,
                dry_run,
                status,
                execution_time,
                json.dumps(result_data) if result_data else None
            ))
            conn.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to insert request log")
            return cursor.lastrowid
    
    def update_request_status(self, request_id: int, status: str, 
                             execution_time: Optional[float] = None, result_data: Optional[dict] = None):
        """Update the status of a logged request."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE request_logs 
                SET status = ?, execution_time = ?, result_data = ?
                WHERE id = ?
            """, (status, execution_time, json.dumps(result_data) if result_data else None, request_id))
            conn.commit()
    
    def add_repository(self, name: str, github_url: str, owner: str, 
                      branch: str = "main", github_token: Optional[str] = None, 
                      local_path: Optional[str] = None, description: Optional[str] = None) -> int:
        """Add a new repository to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO repositories 
                (name, github_url, owner, branch, github_token, local_path, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, github_url, owner, branch, github_token, local_path, description))
            conn.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to insert repository")
            return cursor.lastrowid
    
    def get_repository(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get repository by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM repositories WHERE id = ? AND is_active = 1
            """, (repo_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_repositories(self) -> List[Dict[str, Any]]:
        """Get all active repositories."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM repositories WHERE is_active = 1 ORDER BY name
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def update_repository(self, repo_id: int, **kwargs) -> bool:
        """Update repository information."""
        if not kwargs:
            return False
        
        # Add updated_at timestamp
        kwargs['updated_at'] = datetime.now().isoformat()
        
        # Build dynamic update query
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [repo_id]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f"""
                UPDATE repositories SET {set_clause} WHERE id = ?
            """, values)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_repository(self, repo_id: int) -> bool:
        """Soft delete a repository (mark as inactive)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE repositories SET is_active = 0, updated_at = ? WHERE id = ?
            """, (datetime.now().isoformat(), repo_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def log_aider_execution(self, repo_path: str, instructions: str, 
                           returncode: int, stdout: str, stderr: str, 
                           execution_time: float, repo_id: Optional[int] = None) -> int:
        """Log an aider execution."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO aider_executions 
                (repo_id, repo_path, instructions, returncode, stdout, stderr, execution_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (repo_id, repo_path, instructions, returncode, stdout, stderr, execution_time))
            conn.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to insert aider execution")
            return cursor.lastrowid
    
    def log_api_metric(self, endpoint: str, method: str, status_code: int, response_time: float):
        """Log API performance metrics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO api_metrics (endpoint, method, status_code, response_time)
                VALUES (?, ?, ?, ?)
            """, (endpoint, method, status_code, response_time))
            conn.commit()
    
    def get_recent_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent API requests."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM request_logs 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_repo_history(self, repo_path: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get execution history for a specific repository."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM aider_executions 
                WHERE repo_path = ?
                ORDER BY created_at DESC 
                LIMIT ?
            """, (repo_path, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_api_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get API usage statistics for the last N hours."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT 
                    endpoint,
                    COUNT(*) as request_count,
                    AVG(response_time) as avg_response_time
                FROM api_metrics 
                WHERE datetime(timestamp) > datetime('now', '-{} hours')
                GROUP BY endpoint
            """.format(hours))
            
            endpoint_stats = [dict(row) for row in cursor.fetchall()]
            
            # Get overall stats
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_requests,
                    AVG(response_time) as avg_response_time,
                    MIN(response_time) as min_response_time,
                    MAX(response_time) as max_response_time
                FROM api_metrics 
                WHERE datetime(timestamp) > datetime('now', '-{} hours')
            """.format(hours))
            
            overall_row = cursor.fetchone()
            overall_stats = dict(overall_row) if overall_row else {
                "total_requests": 0,
                "avg_response_time": 0,
                "min_response_time": 0,
                "max_response_time": 0
            }
            
            return {
                "overall": overall_stats,
                "by_endpoint": endpoint_stats
            }
    
    def cleanup_old_logs(self, days: int = 30):
        """Clean up logs older than specified days."""
        with sqlite3.connect(self.db_path) as conn:
            # Clean request logs
            cursor = conn.execute("""
                DELETE FROM request_logs 
                WHERE datetime(created_at) < datetime('now', '-{} days')
            """.format(days))
            requests_deleted = cursor.rowcount
            
            # Clean aider executions
            cursor = conn.execute("""
                DELETE FROM aider_executions 
                WHERE datetime(created_at) < datetime('now', '-{} days')
            """.format(days))
            executions_deleted = cursor.rowcount
            
            # Clean API metrics
            cursor = conn.execute("""
                DELETE FROM api_metrics 
                WHERE datetime(timestamp) < datetime('now', '-{} days')
            """.format(days))
            metrics_deleted = cursor.rowcount
            
            conn.commit()
            
            logger.info(f"Cleaned up {requests_deleted} request logs, "
                       f"{executions_deleted} executions, {metrics_deleted} metrics")
            
            return {
                "requests_deleted": requests_deleted,
                "executions_deleted": executions_deleted,
                "metrics_deleted": metrics_deleted
            }
