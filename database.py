import os
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from models import Base, Repository, AiderExecutionLog, RequestLog, ApiMetricLog, Job, User, BugReport, Vulnerability
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("database")

def to_dict(obj):
    """Convert SQLAlchemy model instance to dictionary."""
    if obj is None:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class RDBMS:
    """
    PostgreSQL database wrapper for the Aider API server.
    Stores request logs, execution history, and basic metrics.
    """

    def __init__(self):
        # Only initialize tables for PostgreSQL using SQLAlchemy
        self.init_db()

    def init_db(self):
        """Create all tables if they don't exist (PostgreSQL)."""
        Base.metadata.create_all(bind=engine)

    def get_session(self) -> Session:
        return SessionLocal()

    def add_repository(self, name: str, github_url: str, owner: str,
                      branch: str = "main", github_token: Optional[str] = None,
                      local_path: Optional[str] = None, description: Optional[str] = None,
                      user_id: Optional[int] = None) -> Optional[int]:
        """Add a new repository to the database."""
        session = self.get_session()
        repo = Repository(
            name=name,
            github_url=github_url,
            owner=owner,
            branch=branch,
            github_token=github_token,
            local_path=local_path,
            description=description,
            is_active=True,
            created_by_user_id=user_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)  # Ensure repo.id is populated with the actual integer value
        repo_id = getattr(repo, "id", None)
        session.close()
        return repo_id

    def get_repository(self, repo_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get repository by ID, optionally checking ownership."""
        session = self.get_session()
        query = session.query(Repository).filter(Repository.id == repo_id, Repository.is_active == True)
        
        if user_id is not None:
            query = query.filter(Repository.created_by_user_id == user_id)
            
        repo = query.first()
        session.close()
        return to_dict(repo) if repo else None

    def get_all_repositories(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all active repositories, optionally filtered by user."""
        session = self.get_session()
        query = session.query(Repository).filter(Repository.is_active == True)
        
        if user_id is not None:
            query = query.filter(Repository.created_by_user_id == user_id)
            
        repos = query.order_by(Repository.name).all()
        session.close()
        return [repo_dict for repo_dict in (to_dict(repo) for repo in repos) if repo_dict is not None]

    def update_repository(self, repo_id: int, user_id: Optional[int] = None, **kwargs) -> bool:
        """Update repository information, optionally checking ownership."""
        session = self.get_session()
        query = session.query(Repository).filter(Repository.id == repo_id)
        if user_id is not None:
            query = query.filter(Repository.created_by_user_id == user_id)
            
        repo = query.first()
        if not repo:
            session.close()
            return False
        for key, value in kwargs.items():
            setattr(repo, key, value)
        setattr(repo, "updated_at", datetime.now())
        session.commit()
        session.close()
        return True

    def delete_repository(self, repo_id: int, user_id: Optional[int] = None) -> bool:
        """Hard delete a repository (remove row from database), optionally checking ownership."""
        session = self.get_session()
        query = session.query(Repository).filter(Repository.id == repo_id)
        if user_id is not None:
            query = query.filter(Repository.created_by_user_id == user_id)
            
        repo = query.first()
        if not repo:
            session.close()
            return False
        session.delete(repo)
        session.commit()
        session.close()
        return True

    def get_repo_history(self, repo_path: str, limit: int = 20):
        session = self.get_session()
        logs = (
            session.query(AiderExecutionLog)
            .filter(AiderExecutionLog.repo_path == repo_path)
            .order_by(AiderExecutionLog.created_at.desc())
            .limit(limit)
            .all()
        )
        session.close()
        return [to_dict(log) for log in logs]  # Use the module-level to_dict

    def update_request_status(self, request_id: int, status: str, execution_time: float, result_data: dict):
        """Update the status, execution time, and result of a request log."""
        session = self.get_session()
        log = session.query(RequestLog).filter(RequestLog.id == request_id).first()
        if log:
            setattr(log, "status", status)  # Assign to the mapped attribute, not the Column object
            setattr(log, "execution_time", execution_time)
            setattr(log, "result_data", str(result_data))  # Store as string or JSON
            session.commit()
        session.close()

    def log_request(self, endpoint: str, repo_id: Optional[int] = None, repo_path: Optional[str] = None,
                    instructions: Optional[str] = None, dry_run: bool = False, status: str = "processing") -> int:
        """Log a new API request and return its ID."""
        session = self.get_session()
        log = RequestLog(
            endpoint=endpoint,
            repo_id=repo_id,
            repo_path=repo_path,
            instructions=instructions,
            dry_run=str(dry_run),
            status=status,
            created_at=datetime.utcnow()
        )
        session.add(log)
        session.commit()
        session.refresh(log)  # Ensure log.id is populated with the actual integer value
        log_id = getattr(log, "id", None)
        session.close()
        if log_id is None:
            raise ValueError("Failed to retrieve log ID after insertion.")
        return log_id

    def log_api_metric(self, endpoint: str, repo_id: int, metric_name: str, metric_value: float):
        """Log an API metric event."""
        session = self.get_session()
        log = ApiMetricLog(
            endpoint=endpoint,
            repo_id=repo_id,
            metric_name=metric_name,
            metric_value=metric_value,
            created_at=datetime.utcnow()
        )
        session.add(log)
        session.commit()
        session.close()

    def log_aider_execution(self, repo_path: str, instructions: str, returncode: int, 
                           stdout: str = "", stderr: str = "", execution_time: Optional[float] = None, 
                           repo_id: Optional[int] = None):
        """Log an Aider execution to the database."""
        session = self.get_session()
        log = AiderExecutionLog(
            repo_path=repo_path,
            instructions=instructions,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            execution_time=execution_time,
            repo_id=repo_id,
            created_at=datetime.utcnow()
        )
        session.add(log)
        session.commit()
        session.close()

    def get_recent_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent API requests, ordered by most recent first."""
        session = self.get_session()
        requests = (
            session.query(RequestLog)
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
            .all()
        )
        session.close()
        return [req_dict for req_dict in (to_dict(req) for req in requests) if req_dict is not None]

    def cleanup_old_logs(self, days: int = 30) -> Dict[str, int]:
        """Delete logs older than specified days. Returns count of deleted records."""
        session = self.get_session()
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Count and delete old request logs
        old_request_logs = session.query(RequestLog).filter(RequestLog.created_at < cutoff_date)
        request_count = old_request_logs.count()
        old_request_logs.delete()
        
        # Count and delete old execution logs
        old_execution_logs = session.query(AiderExecutionLog).filter(AiderExecutionLog.created_at < cutoff_date)
        execution_count = old_execution_logs.count()
        old_execution_logs.delete()
        
        # Count and delete old metric logs
        old_metric_logs = session.query(ApiMetricLog).filter(ApiMetricLog.created_at < cutoff_date)
        metric_count = old_metric_logs.count()
        old_metric_logs.delete()
        
        session.commit()
        session.close()
        
        return {
            "request_logs_deleted": request_count,
            "execution_logs_deleted": execution_count,
            "metric_logs_deleted": metric_count,
            "total_deleted": request_count + execution_count + metric_count
        }

    def get_api_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get API statistics for the specified number of hours."""
        session = self.get_session()
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Total requests in the time period
        total_requests = session.query(RequestLog).filter(RequestLog.created_at >= cutoff_time).count()
        
        # Requests by status
        status_counts = (
            session.query(RequestLog.status, func.count(RequestLog.id))
            .filter(RequestLog.created_at >= cutoff_time)
            .group_by(RequestLog.status)
            .all()
        )
        
        # Requests by endpoint
        endpoint_counts = (
            session.query(RequestLog.endpoint, func.count(RequestLog.id))
            .filter(RequestLog.created_at >= cutoff_time)
            .group_by(RequestLog.endpoint)
            .all()
        )
        
        # Average execution time
        avg_execution_time = (
            session.query(func.avg(RequestLog.execution_time))
            .filter(RequestLog.created_at >= cutoff_time, RequestLog.execution_time.isnot(None))
            .scalar()
        )
        
        # Recent errors
        recent_errors = (
            session.query(RequestLog)
            .filter(RequestLog.created_at >= cutoff_time, RequestLog.status == "error")
            .order_by(RequestLog.created_at.desc())
            .limit(10)
            .all()
        )
        
        session.close()
        
        return {
            "time_period_hours": hours,
            "total_requests": total_requests,
            "status_breakdown": {status: count for status, count in status_counts},
            "endpoint_breakdown": {endpoint: count for endpoint, count in endpoint_counts},
            "average_execution_time": float(avg_execution_time) if avg_execution_time else 0.0,
            "recent_errors": [to_dict(error) for error in recent_errors]
        }

    def create_job(self, repo_id: int, instructions: str, user_id: Optional[int] = None) -> int:
        """Create a new job for a repository."""
        session = self.get_session()
        job = Job(
            repo_id=repo_id,
            user_id=user_id,
            instructions=instructions,
            status="pending"
        )
        session.add(job)
        session.commit()
        session.refresh(job)  # Ensure job.id is populated with the actual integer value
        job_id = getattr(job, "id", None)
        session.close()
        if job_id is None:
            raise ValueError("Failed to retrieve job ID after insertion.")
        return job_id

    def get_user_job_count(self, user_id: int, start_date: Optional[datetime] = None) -> int:
        """Count jobs created by a user since start_date."""
        session = self.get_session()
        query = session.query(Job).filter(Job.user_id == user_id)
        if start_date:
            query = query.filter(Job.created_at >= start_date)
        count = query.count()
        session.close()
        return count

    def get_next_job(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get the next pending job for a repository, ordered by creation time."""
        session = self.get_session()
        job = (
            session.query(Job)
            .filter(Job.repo_id == repo_id, Job.status == "pending")
            .order_by(Job.created_at.asc())
            .first()
        )
        session.close()
        return to_dict(job) if job else None

    def update_job_status(self, job_id: int, status: str, result: Optional[str] = None, error_message: Optional[str] = None):
        """Update job status and results."""
        session = self.get_session()
        job = session.query(Job).filter(Job.id == job_id).first()
        if job:
            setattr(job, "status", status)
            if status == "running" and not getattr(job, "started_at", None):
                setattr(job, "started_at", datetime.utcnow())
            elif status in ["completed", "failed"]:
                setattr(job, "completed_at", datetime.utcnow())
            if result:
                setattr(job, "result", result)
            if error_message:
                setattr(job, "error_message", error_message)
            session.commit()
        session.close()

    def has_running_job(self, repo_id: int) -> bool:
        """Check if repository has a running job."""
        session = self.get_session()
        running = session.query(Job).filter(
            Job.repo_id == repo_id,
            Job.status == "running"
        ).first()
        session.close()
        return running is not None

    def has_completed_awaiting_approval(self, repo_id: int) -> bool:
        """Check if repository has a completed job awaiting approval/rejection."""
        session = self.get_session()
        job = session.query(Job).filter(
            Job.repo_id == repo_id,
            Job.status == "completed"
        ).first()
        session.close()
        return job is not None

    def get_job_status(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get status of a specific job."""
        session = self.get_session()
        job = session.query(Job).filter(Job.id == job_id).first()
        session.close()
        return to_dict(job) if job else None

    def get_repo_jobs(self, repo_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all jobs for a repository."""
        session = self.get_session()
        jobs = (
            session.query(Job)
            .filter(Job.repo_id == repo_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .all()
        )
        session.close()
        return [job_dict for job_dict in (to_dict(job) for job in jobs) if job_dict is not None]

    def get_active_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all active jobs (running + pending only, excluding completed/approved/rejected)."""
        session = self.get_session()
        jobs = (
            session.query(Job)
            .filter(Job.status.in_(["running", "pending"]))
            .order_by(Job.status.desc(), Job.created_at.asc())  # running first, then pending by creation time
            .limit(limit)
            .all()
        )
        session.close()
        # Enrich with repository info
        result = []
        for job in jobs:
            job_dict = to_dict(job)
            if job_dict:
                # Get repository info
                repo = self.get_repository(job_dict['repo_id'])
                if repo:
                    job_dict['repo_name'] = repo.get('name', 'Unknown')
                    job_dict['repo_github_url'] = repo.get('github_url', '')
                result.append(job_dict)
        return result
    def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Google ID."""
        session = self.get_session()
        user = session.query(User).filter(User.google_id == google_id).first()
        session.close()
        return to_dict(user) if user else None

    def log_bug(self, error_type: str, error_message: str, stack_trace: str = None, endpoint: str = None, user_id: int = None) -> int:
        """Log a bug report to the database."""
        session = self.get_session()
        try:
            bug = BugReport(
                error_type=error_type,
                error_message=error_message,
                stack_trace=stack_trace,
                endpoint=endpoint,
                user_id=user_id,
                created_at=datetime.utcnow()
            )
            session.add(bug)
            session.commit()
            session.refresh(bug)
            bug_id = bug.id
            return bug_id
        except Exception as e:
            logger.error(f"Failed to log bug: {e}")
            return None
        finally:
            session.close()

    def update_bug_status(self, bug_id: int, status: str) -> bool:
        """Update the status of a bug report."""
        session = self.get_session()
        try:
            bug = session.query(BugReport).filter(BugReport.id == bug_id).first()
            if bug:
                bug.status = status
                session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update bug status: {e}")
            return False
        finally:
            session.close()

    def get_bug_reports(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent bug reports, optionally filtered by status."""
        session = self.get_session()
        try:
            query = session.query(BugReport)
            if status:
                query = query.filter(BugReport.status == status)
            
            bugs = query.order_by(BugReport.created_at.desc()).limit(limit).all()
            return [to_dict(bug) for bug in bugs]
        except Exception as e:
            logger.error(f"Failed to get bug reports: {e}")
            return []
        finally:
            session.close()

    def get_repository_by_local_path(self, local_path: str) -> Optional[Dict[str, Any]]:
        """Get repository by local path."""
        session = self.get_session()
        try:
            # Normalize path for comparison
            norm_path = os.path.normpath(local_path)
            repos = session.query(Repository).filter(Repository.is_active == True).all()
            
            for repo in repos:
                if repo.local_path and os.path.normpath(repo.local_path) == norm_path:
                    return to_dict(repo)
            return None
        finally:
            session.close()

    def log_vulnerability(self, repo_id: int, file_path: str, description: str, 
                         severity: str = "medium", line_number: Optional[int] = None, 
                         pattern_id: Optional[str] = None, branch: str = "HEAD") -> int:
        """Log a security vulnerability."""
        session = self.get_session()
        vuln = Vulnerability(
            repo_id=repo_id,
            file_path=file_path,
            description=description,
            severity=severity,
            line_number=line_number,
            pattern_id=pattern_id,
            branch=branch,
            status="open",
            created_at=datetime.utcnow()
        )
        session.add(vuln)
        session.commit()
        session.refresh(vuln)
        vuln_id = getattr(vuln, "id", None)
        session.close()
        return vuln_id

    def get_vulnerabilities(self, repo_id: int, status: Optional[str] = None, branch: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get vulnerabilities for a repository."""
        session = self.get_session()
        query = session.query(Vulnerability).filter(Vulnerability.repo_id == repo_id)
        if status:
            query = query.filter(Vulnerability.status == status)
        if branch:
            query = query.filter(Vulnerability.branch == branch)
        vulns = query.order_by(Vulnerability.severity.desc(), Vulnerability.created_at.desc()).all()
        session.close()
        return [to_dict(v) for v in vulns]

    def update_vulnerability_status(self, vuln_id: int, status: str) -> bool:
        """Update vulnerability status."""
        session = self.get_session()
        vuln = session.query(Vulnerability).filter(Vulnerability.id == vuln_id).first()
        if not vuln:
            session.close()
            return False
        
        vuln.status = status
        if status == "resolved":
            vuln.resolved_at = datetime.utcnow()
            
        session.commit()
        session.close()
        return True

    def get_vulnerability(self, vuln_id: int) -> Optional[Dict[str, Any]]:
        """Get a single vulnerability by ID."""
        session = self.get_session()
        vuln = session.query(Vulnerability).filter(Vulnerability.id == vuln_id).first()
        session.close()
        return to_dict(vuln) if vuln else None
