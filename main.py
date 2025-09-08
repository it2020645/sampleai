# server.py
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from pydantic import BaseModel
import subprocess
import shlex
import os
from pathlib import Path
import logging
import uvicorn
from typing import Optional
import time
from database import LightDatabase

# === CONFIG ===
API_KEY = "change_this_to_a_strong_key"   # change this before running
ALLOWED_BASE = Path("C:/Users/batal/OneDrive/Documents/GitHub/ai").resolve()  # base folder for repositories
AIDER_CMD = "aider"  # assume aider is on PATH (or provide full path)
TIMEOUT_SECONDS = 300  # max seconds to let aider run

# === ENDPOINTS ===
ENDPOINT_UPDATE_CODE = "/update-code"
ENDPOINT_UPDATE_CODE_BY_ID = "/update-code-by-id"
ENDPOINT_STATUS = "/status"
ENDPOINT_EXEC = "/exec"

# === ERROR MESSAGES ===
ERROR_MISSING_AUTH = "Missing Authorization header"
ERROR_INVALID_KEY = "Invalid API key"
ERROR_REPO_NOT_FOUND = "Repository not found"

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aider_server")

# === Database ===
db = LightDatabase()

# Ensure the base directory exists
ALLOWED_BASE.mkdir(parents=True, exist_ok=True)
logger.info(f"Base directory ensured: {ALLOWED_BASE}")

app = FastAPI(title="Aider Wrapper API")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

class UpdateRequest(BaseModel):
    repo: str                # path relative to ALLOWED_BASE, or absolute (validated)
    instructions: str        # the prompt/instructions to feed to aider
    dry_run: Optional[bool] = False  # if true, don't write changes (if aider supports such mode)

class UpdateByIdRequest(BaseModel):
    repo_id: int             # repository ID from database
    instructions: str        # the prompt/instructions to feed to aider
    dry_run: Optional[bool] = False  # if true, don't write changes

class RepositoryRequest(BaseModel):
    name: str
    github_url: str
    owner: str
    branch: str = "main"
    github_token: Optional[str] = None
    local_path: Optional[str] = None
    description: Optional[str] = None

def validate_and_resolve_repo(repo_path: str) -> Path:
    """
    Ensure the repo_path is inside ALLOWED_BASE. Accept either absolute or
    relative paths. Return resolved Path.
    """
    p = Path(repo_path)
    if not p.is_absolute():
        p = ALLOWED_BASE / p
    p = p.resolve()
    # Ensure the resolved path is inside ALLOWED_BASE
    try:
        p.relative_to(ALLOWED_BASE)
    except Exception:
        raise HTTPException(status_code=400, detail="Repo path not allowed")
    if not p.exists():
        raise HTTPException(status_code=400, detail="Repo path does not exist")
    if not (p / ".git").exists():
        # Not strictly required, but helpful to ensure it's a git repo
        logger.warning("Repo path does not contain .git - continuing anyway.")
    return p

def run_aider(repo_path: Path, instructions: str, dry_run: bool=False, repo_id: Optional[int] = None):
    """
    Run the aider CLI in the given repository, feeding instructions via stdin.
    Capture stdout/stderr and return them.
    """
    start_time = time.time()
    cmd = [AIDER_CMD, "--yes", "--repo", str(repo_path)]
    
    # If aider has a dry-run flag, you could pass it based on `dry_run` here.
    if dry_run:
        logger.info("Dry run mode - would execute aider but not making actual changes")
    
    logger.info(f"Running aider: {' '.join(shlex.quote(p) for p in cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            input=instructions,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        
        execution_time = time.time() - start_time
        
        # Log to database
        db.log_aider_execution(
            repo_path=str(repo_path),
            instructions=instructions,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            execution_time=execution_time,
            repo_id=repo_id
        )
        
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "execution_time": execution_time,
        }
    except subprocess.TimeoutExpired as e:
        execution_time = time.time() - start_time
        logger.error("Aider timed out")
        
        # Log timeout to database
        db.log_aider_execution(
            repo_path=str(repo_path),
            instructions=instructions,
            returncode=-1,
            stdout="",
            stderr=f"Timeout after {TIMEOUT_SECONDS}s",
            execution_time=execution_time,
            repo_id=repo_id
        )
        
        return {"error": "timeout", "message": str(e), "execution_time": execution_time}

# === Endpoints ===

@app.get("/")
async def root():
    """Serve the frontend interface."""
    return FileResponse('static/index.html')

@app.get("/status")
async def status():
    return {"ok": True, "message": "Aider wrapper running", "database": "connected"}

# Repository Management Endpoints
@app.post("/repositories")
async def add_repository(repo: RepositoryRequest, authorization: Optional[str] = Header(None)):
    """Add a new repository."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    try:
        # Auto-generate local path if not provided (format: base_path/owner/repo_name)
        local_path = repo.local_path
        if not local_path:
            local_path = str(ALLOWED_BASE / repo.owner / repo.name)
        
        repo_id = db.add_repository(
            name=repo.name,
            github_url=repo.github_url,
            owner=repo.owner,
            branch=repo.branch,
            github_token=repo.github_token,
            local_path=local_path,
            description=repo.description
        )
        return {"status": "success", "repo_id": repo_id, "message": "Repository added successfully", "local_path": local_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/repositories")
async def get_repositories(authorization: Optional[str] = Header(None)):
    """Get all repositories."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    repos = db.get_all_repositories()
    return repos

@app.get("/repositories/{repo_id}")
async def get_repository(repo_id: int, authorization: Optional[str] = Header(None)):
    """Get a specific repository."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    return repo

@app.delete("/repositories/{repo_id}")
async def delete_repository(repo_id: int, authorization: Optional[str] = Header(None)):
    """Delete a repository."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    success = db.delete_repository(repo_id)
    if not success:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    return {"status": "success", "message": "Repository deleted successfully"}

@app.post("/update-code-by-id")
async def update_code_by_id(req: UpdateByIdRequest, authorization: Optional[str] = Header(None)):
    """Update code using repository ID instead of path."""
    start_time = time.time()
    
    # Authentication
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)

    # Get repository info
    repo = db.get_repository(req.repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    
    # Determine repo path
    if repo['local_path']:
        repo_path = Path(repo['local_path'])
    else:
        # Use default path construction with owner/repo structure
        repo_path = ALLOWED_BASE / repo['owner'] / repo['name']
    
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Repository path does not exist: {repo_path}")

    # Log request to database
    request_id = db.log_request(
        endpoint=ENDPOINT_UPDATE_CODE_BY_ID,
        repo_id=req.repo_id,
        repo_path=str(repo_path),
        instructions=req.instructions,
        dry_run=req.dry_run if req.dry_run is not None else False,
        status="processing"
    )

    try:
        # Run aider
        result = run_aider(repo_path, req.instructions, dry_run=req.dry_run if req.dry_run is not None else False, repo_id=req.repo_id)
        
        execution_time = time.time() - start_time
        
        # Update request status
        db.update_request_status(
            request_id=request_id,
            status="completed" if "error" not in result else "failed",
            execution_time=execution_time,
            result_data=result
        )
        
        # Log API metrics
        db.log_api_metric(
            endpoint=ENDPOINT_UPDATE_CODE_BY_ID,
            method="POST",
            status_code=200,
            response_time=execution_time
        )

        return {
            "status": "done", 
            "repo": repo['name'], 
            "repo_id": req.repo_id,
            "result": result, 
            "request_id": request_id
        }
    
    except Exception as e:
        execution_time = time.time() - start_time
        error_result = {"error": "internal_error", "message": str(e)}
        
        # Update request status with error
        db.update_request_status(
            request_id=request_id,
            status="error",
            execution_time=execution_time,
            result_data=error_result
        )
        
        # Log API metrics
        db.log_api_metric(
            endpoint=ENDPOINT_UPDATE_CODE_BY_ID,
            method="POST",
            status_code=500,
            response_time=execution_time
        )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs(limit: int = 50, authorization: Optional[str] = Header(None)):
    """Get recent API request logs."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")
    
    logs = db.get_recent_requests(limit)
    return {"logs": logs}

@app.get("/repo/{repo_name}/history")
async def get_repo_history(repo_name: str, limit: int = 20, authorization: Optional[str] = Header(None)):
    """Get execution history for a specific repository."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")
    
    # Construct full repo path
    repo_path = str(ALLOWED_BASE / repo_name)
    history = db.get_repo_history(repo_path, limit)
    return {"repo": repo_name, "history": history}

@app.get("/stats")
async def get_stats(hours: int = 24, authorization: Optional[str] = Header(None)):
    """Get API usage statistics."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")
    
    stats = db.get_api_stats(hours)
    return {"stats": stats, "period_hours": hours}

@app.delete("/logs/cleanup")
async def cleanup_logs(days: int = 30, authorization: Optional[str] = Header(None)):
    """Clean up old logs."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")
    
    result = db.cleanup_old_logs(days)
    return {"cleanup_result": result, "days": days}

@app.post("/update-code")
async def update_code(req: UpdateRequest, authorization: Optional[str] = Header(None)):
    start_time = time.time()
    
    # Basic API key auth: expect header Authorization: Bearer <API_KEY>
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    # support either "Bearer KEY" or just the key
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")

    # Validate repo path
    repo_path = validate_and_resolve_repo(req.repo)
    logger.info(f"Received update request for repo: {repo_path}")

    # Log request to database
    request_id = db.log_request(
        endpoint=ENDPOINT_UPDATE_CODE,
        repo_path=str(repo_path),
        instructions=req.instructions,
        dry_run=req.dry_run if req.dry_run is not None else False,
        status="processing"
    )

    try:
        # Run aider
        result = run_aider(repo_path, req.instructions, dry_run=req.dry_run if req.dry_run is not None else False)
        
        execution_time = time.time() - start_time
        
        # Update request status
        db.update_request_status(
            request_id=request_id,
            status="completed" if "error" not in result else "failed",
            execution_time=execution_time,
            result_data=result
        )
        
        # Log API metrics
        db.log_api_metric(
            endpoint=ENDPOINT_UPDATE_CODE,
            method="POST",
            status_code=200,
            response_time=execution_time
        )

        return {"status": "done", "repo": str(repo_path), "result": result, "request_id": request_id}
    
    except Exception as e:
        execution_time = time.time() - start_time
        error_result = {"error": "internal_error", "message": str(e)}
        
        # Update request status with error
        db.update_request_status(
            request_id=request_id,
            status="error",
            execution_time=execution_time,
            result_data=error_result
        )
        
        # Log API metrics
        db.log_api_metric(
            endpoint=ENDPOINT_UPDATE_CODE,
            method="POST",
            status_code=500,
            response_time=execution_time
        )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/exec")
async def exec_command(payload: dict, authorization: Optional[str] = Header(None)):
    """
    A low-level endpoint for debugging / special commands.
    NOT recommended for production. Kept here for convenience.
    """
    def validate_authorization(auth_header):
        if not auth_header:
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
        token = auth_header.split()[-1]
        if token != API_KEY:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API key")

    def validate_cwd(cwd):
        p = Path(cwd)
        if not p.is_absolute():
            p = ALLOWED_BASE / p
        p = p.resolve()
        try:
            p.relative_to(ALLOWED_BASE)
        except Exception:
            raise HTTPException(status_code=400, detail="cwd not allowed")
        return p

    def execute_command(cmd, cwd_path):
        try:
            proc = subprocess.run(shlex.split(cmd), cwd=str(cwd_path), capture_output=True, text=True, timeout=60)
            return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    validate_authorization(authorization)
    cmd = payload.get("cmd")
    cwd = payload.get("cwd", str(ALLOWED_BASE))
    if not cmd:
        raise HTTPException(status_code=400, detail="No cmd provided")
    cwd_path = validate_cwd(cwd)
    logger.info(f"Exec debug command in {cwd_path}: {cmd}")
    return execute_command(cmd, cwd_path)

# Run by uvicorn when invoked directly
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
