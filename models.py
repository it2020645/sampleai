from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    picture_url = Column(String, nullable=True)
    plan_type = Column(String, default="free")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Repository(Base):
    __tablename__ = "repositories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    github_url = Column(String, unique=True, nullable=False)
    owner = Column(String, nullable=False)
    branch = Column(String, default="main")
    github_token = Column(String, nullable=True)
    local_path = Column(String)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey('repositories.id'), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), index=True, nullable=True)
    instructions = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending, running, completed, failed
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

class RequestLog(Base):
    __tablename__ = "request_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String)
    repo_id = Column(Integer)
    repo_path = Column(String)
    instructions = Column(Text)
    dry_run = Column(String)
    status = Column(String)
    execution_time = Column(Float)
    result_data = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class AiderExecutionLog(Base):
    __tablename__ = "aider_execution_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    repo_path = Column(String, index=True)
    instructions = Column(Text)
    returncode = Column(Integer)
    stdout = Column(Text)
    stderr = Column(Text)
    execution_time = Column(Integer)
    repo_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class ApiMetricLog(Base):
    __tablename__ = "api_metric_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String)
    repo_id = Column(Integer)
    metric_name = Column(String)
    metric_value = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class BugReport(Base):
    __tablename__ = "bug_reports"

    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String, nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    endpoint = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="open")  # open, in_progress, resolved, closed

class Vulnerability(Base):
    __tablename__ = "vulnerabilities"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey('repositories.id'), nullable=False)
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=True)
    severity = Column(String, default="medium")  # low, medium, high, critical
    description = Column(Text, nullable=False)
    pattern_id = Column(String, nullable=True)  # e.g., 'hardcoded_secret'
    branch = Column(String, default="HEAD")
    status = Column(String, default="open")  # open, in_progress, resolved, false_positive
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)