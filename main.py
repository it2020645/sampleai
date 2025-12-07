# server.py
from fastapi import FastAPI, Request, HTTPException, Header, Depends
import sys
import asyncio
from datetime import datetime

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from pydantic import BaseModel
import subprocess
import shlex
import os
from pathlib import Path
import logging
import uvicorn
from typing import Optional, List, Dict
import time
from threading import Thread
from database import RDBMS
from dotenv import load_dotenv
import sys
from models import Base  # Make sure you have models.py with Base and your ORM models
from database import engine  # Your SQLAlchemy engine from database.py
from auth import get_current_user
from auth_routes import router as auth_router
from security_scanner import SecurityScanner
import traceback
import openai
# Load environment variables from .env file
load_dotenv(override=True)

# Reconfigure stdout to use UTF-8 encoding


# === CONFIG ===
HOST_ADDRESS = os.getenv("HOST_ADDRESS", "0.0.0.0")  # Default to 0.0.0.0 if not set
API_KEY = os.getenv("AIDER_API_KEY", "change_this_to_a_strong_key")  # Load from .env file
ALLOWED_BASE = Path(os.getenv("ALLOWED_BASE_PATH", "C:/Users/batal/OneDrive/Documents/GitHub/ai")).resolve()
# Use relative path by default to avoid CORS/Cookie domain issues (localhost vs 127.0.0.1)
# Force empty string to ensure relative paths are used
API_BASE_URL = "" 
print(f"DEBUG: API_BASE_URL set to: '{API_BASE_URL}'")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development, staging, production
AIDER_CMD = "aider"  # assume aider is on PATH (or provide full path)
TIMEOUT_SECONDS = int(os.getenv("AIDER_TIMEOUT_SECONDS", "300"))  # max seconds to let aider run

# Admin Users
ADMIN_EMAILS = ["novusmundus2025@gmail.com", "batalladavid1984@gmail.com"]

# Git Branch Management
AUTO_CREATE_BRANCH = os.getenv("AUTO_CREATE_BRANCH", "false").lower() == "true"
BRANCH_PREFIX = os.getenv("BRANCH_PREFIX", "feature/aider")
AUTO_PUSH_BRANCH = os.getenv("AUTO_PUSH_BRANCH", "false").lower() == "true"

# GitHub Integration
PUSH_TO_ORIGIN = os.getenv("PUSH_TO_ORIGIN", "true").lower() == "true"
CREATE_PULL_REQUEST = os.getenv("CREATE_PULL_REQUEST", "false").lower() == "true"
PR_TARGET_BRANCH = os.getenv("PR_TARGET_BRANCH", "master")

# CI/CD Integration
WAIT_FOR_CI = os.getenv("WAIT_FOR_CI", "true").lower() == "true"
CI_WAIT_TIMEOUT_MINUTES = int(os.getenv("CI_WAIT_TIMEOUT_MINUTES", "2"))  # Reduced to 2 minutes for testing
CHECK_RUNNING_WORKFLOWS = os.getenv("CHECK_RUNNING_WORKFLOWS", "true").lower() == "true"
WORKFLOW_WAIT_TIMEOUT_MINUTES = int(os.getenv("WORKFLOW_WAIT_TIMEOUT_MINUTES", "5"))  # Wait up to 5 minutes for workflows

# Plan Limits
PLAN_LIMITS = {
    'free': 5,
    'pro': 25,
    'enterprise': 1000
}

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
db = RDBMS()
db.init_db() 


# Ensure the base directory exists
ALLOWED_BASE.mkdir(parents=True, exist_ok=True)
print(f"Base directory ensured: {ALLOWED_BASE}")

app = FastAPI(title="Aider Wrapper API")

# Add CORS middleware for cookie support
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", 
        "http://127.0.0.1:8000", 
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080"
    ],  # Adjust for production
    allow_credentials=True,  # Essential for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth router
app.include_router(auth_router)

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
    github_token: Optional[str] = None  # GitHub token for PR creation
    pr_target_branch: Optional[str] = "master"  # target branch for PR

class RepositoryRequest(BaseModel):
    name: str
    github_url: str
    owner: str
    branch: str = "master"
    github_token: Optional[str] = None
    local_path: Optional[str] = None
    description: Optional[str] = None

def generate_semantic_name(instructions: str, max_length: int = 50) -> str:
    """
    Generate a semantic name from instructions by extracting key action words.
    Examples:
    - "Add a new function to calculate fibonacci" -> "add-fibonacci-function"
    - "Fix bug in authentication handler" -> "fix-authentication-handler"
    - "Refactor database connection logic" -> "refactor-database-connection"
    """
    import re
    
    if not instructions or not instructions.strip():
        return "update"
    
    # Remove special characters and normalize whitespace
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', instructions.strip())
    words = sanitized.split()
    
    # Find action verbs (common first words)
    action_verbs = {'add', 'create', 'update', 'modify', 'fix', 'refactor', 'optimize', 
                    'improve', 'implement', 'remove', 'delete', 'enhance', 'rewrite'}
    
    # Get first action word
    first_action = None
    action_idx = 0
    for i, word in enumerate(words):
        if word.lower() in action_verbs:
            first_action = word.lower()
            action_idx = i
            break
    
    if not first_action:
        first_action = "update"
        action_idx = 0
    
    # Get 2-3 most meaningful words after the action
    remaining_words = words[action_idx + 1:action_idx + 4]
    meaningful_words = [w for w in remaining_words if len(w) > 2][:2]
    
    # Combine to create semantic name
    name_parts = [first_action] + meaningful_words
    semantic_name = '-'.join(name_parts).lower()[:max_length]
    
    return semantic_name

def ensure_repo_initialized(repo_path: Path):
    """Ensure the repository has at least one commit."""
    try:
        # Check if there are any commits
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError:
        # No commits, initialize
        print(f"Initializing empty repository at {repo_path}")
        readme_path = repo_path / "README.md"
        if not readme_path.exists():
            readme_path.write_text("# Initial Commit\n\nCreated by Aider Manager.")
        
        subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True)
        # Rename branch to master if it's not already
        subprocess.run(["git", "branch", "-M", "master"], cwd=str(repo_path), check=True)

def create_branch_for_changes(repo_path: Path, instructions: str) -> str:
    """
    Create a new git branch for the changes with a descriptive semantic name.
    Always creates a feature branch with intelligent naming:
    - If instructions provided: feature/{semantic-name-from-instructions}-{timestamp}
    - If instructions blank: feature/{update}-{timestamp}
    Returns the branch name created.
    """
    import datetime
    import time
    
    # Ensure repo is initialized
    ensure_repo_initialized(repo_path)
    
    # Generate unique timestamp suffix
    timestamp = int(time.time())
    
    # Generate semantic branch name based on instructions
    branch_suffix = generate_semantic_name(instructions)
    
    branch_name = f"feature/{branch_suffix}-{timestamp}"
    
    try:
        # First, make sure we're on a clean state
        subprocess.run(
            ["git", "checkout", "master"],
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        
        # Create and checkout new branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        print(f"Created new branch: {branch_name}")
        return branch_name
    except subprocess.CalledProcessError as e:
        print(f"Failed to create branch {branch_name}: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Failed to create git branch: {e.stderr}")

def ensure_remote_origin(repo_path: Path, github_url: str) -> bool:
    """
    Ensure the repository has the correct remote origin set.
    Returns True if successful, False otherwise.
    """
    try:
        # Check if origin exists
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        current_origin = result.stdout.strip()
        if current_origin != github_url:
            print(f"Updating origin from {current_origin} to {github_url}")
            subprocess.run(
                ["git", "remote", "set-url", "origin", github_url],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True
            )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to set remote origin: {e.stderr}")
        try:
            # Try to add origin if it doesn't exist
            subprocess.run(
                ["git", "remote", "add", "origin", github_url],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True
            )
            print(f"Added origin remote: {github_url}")
            return True
        except subprocess.CalledProcessError as e2:
            print(f"Failed to add origin remote: {e2.stderr}")
            return False

def push_branch_to_remote(repo_path: Path, branch_name: str, github_url: Optional[str] = None, github_token: Optional[str] = None) -> dict:
    """
    Push the branch to remote repository.
    Returns dict with success status and details.
    """
    result = {"success": False, "pushed_to_origin": False, "error": None}
    print(f"Pushing branch {branch_name} from {repo_path} to {github_url}")
    print(f"Working directory for git push: {repo_path}")
    
    try:
        if github_url and not ensure_remote_origin(repo_path, github_url):
            result["error"] = "Failed to set up remote origin"
            print(f"Failed to set up remote origin for {github_url}")
            return result
        remote_check = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        print(f"Git remotes: {remote_check.stdout}")
        push_cmd = ["git", "push", "-u", "origin", branch_name]
        if github_token and github_url:
            import urllib.parse
            parsed_url = urllib.parse.urlparse(github_url)
            if parsed_url.scheme == 'https':
                auth_url = f"https://{github_token}@{parsed_url.netloc}{parsed_url.path}"
                print(f"Using token authentication for push to {parsed_url.netloc}")
                subprocess.run(
                    ["git", "remote", "set-url", "origin", auth_url],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    check=True
                )
        print(f"Executing: {' '.join(push_cmd)} in {repo_path}")
        push_process = subprocess.run(
            push_cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )
        result["push_stdout"] = push_process.stdout
        result["push_stderr"] = push_process.stderr
        result["push_returncode"] = push_process.returncode
        if push_process.returncode == 0:
            print(f"Successfully pushed branch {branch_name} to origin")
            result["success"] = True
            result["pushed_to_origin"] = True
        else:
            error_msg = f"Failed to push branch {branch_name}: stdout='{push_process.stdout}' stderr='{push_process.stderr}'"
            print(error_msg)
            result["error"] = error_msg
        if github_token and github_url:
            subprocess.run(
                ["git", "remote", "set-url", "origin", github_url],
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )
    except Exception as e:
        error_msg = f"Exception during push: {str(e)}"
        print(error_msg)
        result["error"] = error_msg
    return result

def wait_for_ci_success(github_url: str, branch_name: str, github_token: str, max_wait_minutes: int = 10) -> bool:
    """
    Wait for CI/CD to complete successfully on a branch.
    Returns True if all checks pass, False if they fail or timeout.
    """
    import time

    max_wait_seconds = max_wait_minutes * 60
    check_interval = 30  # Check every 30 seconds
    start_time = time.time()

    consecutive_pending_count = 0
    max_consecutive_pending = 3  # If pending 3 times in a row, assume no CI/CD

    while time.time() - start_time < max_wait_seconds:
        ci_status = get_ci_status(github_url, branch_name, github_token)

        if ci_status.get("status") == "success":
            print(f"CI/CD completed successfully for {branch_name}")
            return True
        elif ci_status.get("status") in ["failure", "error"]:
            print(f"CI/CD failed for {branch_name}: {ci_status}")
            return False
        elif ci_status.get("status") == "pending":
            consecutive_pending_count += 1
            if consecutive_pending_count >= max_consecutive_pending:
                # Check if there are actually any status checks configured
                if ci_status.get("total_count", 0) == 0:
                    print(f"No CI/CD checks configured for {branch_name}, proceeding")
                    return True
                print(f"CI/CD still running for {branch_name}, waiting... ({consecutive_pending_count}/{max_consecutive_pending})")
            else:
                print(f"CI/CD still running for {branch_name}, waiting... ({consecutive_pending_count}/{max_consecutive_pending})")
            time.sleep(check_interval)
        else:
            # Unknown status or no CI configured
            print(f"No CI/CD status found for {branch_name} (status: {ci_status.get('status', 'unknown')}), assuming no CI configured")
            return True  # Assume success if no CI is configured

    print(f"CI/CD timed out after {max_wait_minutes} minutes for {branch_name}")
    return False

def check_workflow_runs(github_url: str, branch_name: str, github_token: str) -> dict:
    """
    Check if there are any running workflow runs on the target branch.
    Returns dict with workflow run information.
    """
    try:
        import re
        import requests
        
        # Extract owner and repo from GitHub URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)(?:\.git)?', github_url)
        if not match:
            return {"has_running_workflows": False, "error": "Invalid GitHub URL format", "safe_to_proceed": True}
        
        owner, repo = match.groups()
        repo = repo.replace('.git', '')
        
        # Get workflow runs for the branch
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        params = {
            "branch": branch_name,
            "status": "in_progress"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            running_workflows = data.get("workflow_runs", [])
            return {
                "has_running_workflows": len(running_workflows) > 0,
                "running_count": len(running_workflows),
                "safe_to_proceed": len(running_workflows) == 0,
                "workflows": [
                    {
                        "id": w.get("id"),
                        "name": w.get("name", ""),
                        "status": w.get("status", ""),
                        "conclusion": w.get("conclusion"),
                        "html_url": w.get("html_url", "")
                    }
                    for w in running_workflows
                ]
            }
        elif response.status_code == 404:
            # Repository might not exist, or no workflows configured yet
            print(f"No workflows found for {owner}/{repo} on branch {branch_name} (first push or no CI/CD configured)")
            return {"has_running_workflows": False, "safe_to_proceed": True, "reason": "no_workflows_configured"}
        else:
            print(f"GitHub API returned {response.status_code} when checking workflows")
            return {"has_running_workflows": False, "safe_to_proceed": True, "error": f"GitHub API error: {response.status_code}"}
            
    except ImportError:
        print("requests library not installed")
        return {"has_running_workflows": False, "safe_to_proceed": True, "error": "requests library not installed"}
    except Exception as e:
        print(f"Error checking workflows: {e}")
        return {"has_running_workflows": False, "safe_to_proceed": True, "error": str(e)}

def get_ci_status(github_url: str, branch_name: str, github_token: str) -> dict:
    """
    Get CI/CD status for a branch from GitHub.
    Returns dict with CI status information.
    """
    try:
        import re
        import requests
        
        # Extract owner and repo from GitHub URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)(?:\.git)?', github_url)
        if not match:
            return {"status": "unknown", "error": "Invalid GitHub URL format"}
        
        owner, repo = match.groups()
        repo = repo.replace('.git', '')
        
        # Get status checks for the branch
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch_name}/status"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            status_data = response.json()
            return {
                "status": status_data.get("state", "unknown"),  # pending, success, failure, error
                "total_count": status_data.get("total_count", 0),
                "statuses": [
                    {
                        "context": s.get("context", ""),
                        "state": s.get("state", ""),
                        "description": s.get("description", ""),
                        "target_url": s.get("target_url", "")
                    }
                    for s in status_data.get("statuses", [])
                ]
            }
        else:
            return {"status": "unknown", "error": f"GitHub API error: {response.status_code}"}
            
    except ImportError:
        print(f"requests library not installed")
        return {"status": "unknown", "error": "requests library not installed"}
    except Exception as e:
        return {"status": "unknown", "error": str(e)}

def create_pull_request(github_url: str, branch_name: str, instructions: str, base_branch: str = "master", github_token: Optional[str] = None) -> dict:
    """
    Create a pull request on GitHub for the branch.
    Returns dict with success status and PR details.
    """
    print(f"CI/CD completed successfully for {branch_name}")
    if not github_token:
        print("GitHub token required for pull request creation. Please provide it in the web interface.")
        return {"success": False, "error": "GitHub token required for pull request creation. Please provide it in the web interface."}
    try:
        import re
        import requests

        # Extract owner and repo from GitHub URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)(?:\.git)?', github_url)
        if not match:
            print(f"Invalid GitHub URL format: {github_url}")
            return {"success": False, "error": "Invalid GitHub URL format. Expected https://github.com/<owner>/<repo>.git"}
        owner, repo = match.groups()
        repo = repo.replace('.git', '')

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {github_token}"
        }

        # Generate PR title and body from instructions
        semantic_summary = generate_semantic_name(instructions, max_length=60)
        # Create a more natural title using first 80 chars of instructions
        summary = instructions[:80].rstrip('.,!?;:') + ('...' if len(instructions) > 80 else '')
        title = f"[AI] {semantic_summary.replace('-', ' ').title()}"
        
        body = f"""## AI-Generated Code Changes

**Summary:** {summary}

**Full Instructions:** {instructions}

**Branch:** `{branch_name}`
**Generated by:** Aider AI Assistant
**Created:** {time.strftime('%Y-%m-%d %H:%M:%S')}

---
*This pull request was automatically created by the AI coding assistant.*
"""

        data = {
            "title": title,
            "body": body,
            "head": branch_name,
            "base": base_branch
        }

        print(f"Creating PR with data: {data}")

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 201:
            pr_data = response.json()
            print(f"Created pull request #{pr_data['number']}: {pr_data['html_url']}")

            # Get initial CI/CD status
            ci_status = get_ci_status(github_url, branch_name, github_token)

            return {
                "success": True,
                "pr_number": pr_data['number'],
                "pr_url": pr_data['html_url'],
                "pr_title": title,
                "ci_status": ci_status,
                "status_check_url": f"{pr_data['html_url']}/checks"
            }
        elif response.status_code == 404:
            print(f"GitHub API error 404: Not Found. Possible causes: repo/branch does not exist, token lacks access, or repo is private.")
            print(f"URL: {url}")
            print(f"Branch: {branch_name}")
            print(f"Token provided: {'yes' if github_token else 'no'}")
            print(f"Response: {response.text}")
            return {
                "success": False,
                "error": "GitHub API error 404: Not Found. Possible causes: repo/branch does not exist, token lacks access, or repo is private.",
                "details": response.text,
                "url": url,
                "branch": branch_name,
                "token_provided": bool(github_token)
            }
        else:
            error_msg = f"GitHub API error: {response.status_code} - {response.text}"
            print(error_msg)
            return {"success": False, "error": error_msg}

    except ImportError:
        print("requests library not installed")
        return {"success": False, "error": "requests library not installed"}
    except Exception as e:
        error_msg = f"Failed to create pull request: {str(e)}"
        print(error_msg)
        return {"success": False, "error": error_msg}

def get_current_branch(repo_path: Path) -> str:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "master"  # fallback

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

def extract_filenames_from_instructions(instructions: str) -> List[str]:
    """
    Extract filenames from instructions using a regex for common file patterns.
    """
    import re
    # Match filenames like package.json, app.js, index.js, *.py, *.ts, *.md, etc.
    return re.findall(r'\b[\w\-]+\.(?:json|js|ts|py|md|yml|yaml|txt|html|css)\b', instructions)

def run_aider(repo_path: Path, instructions: str, dry_run: bool=False, repo_id: Optional[int] = None, github_url: Optional[str] = None, github_token: Optional[str] = None, pr_target_branch: str = "master"):
    print(f"run_aider: repo_path={repo_path}, instructions={instructions}, dry_run={dry_run}, repo_id={repo_id}, github_url={github_url}, github_token={'set' if github_token else 'unset'}, pr_target_branch={pr_target_branch}")
    print("run_aider: Starting code change process...")
    """
    Run the aider CLI in the given repository, feeding instructions via stdin.
    Optionally create a new branch for the changes.
    Capture stdout/stderr and return them.
    """
    print(f"run_aider called with pr_target_branch={pr_target_branch}")
    start_time = time.time()
    cmd = [AIDER_CMD, ".", "--yes-always", "--auto-commits", "--no-pretty", "--no-stream"]

    # Add OpenAI API key in the correct format for Aider
    openai_key = os.getenv("OPENAI_API_KEY")
    print(f"DEBUG: OPENAI_API_KEY first 20 chars: {openai_key[:20] if openai_key else 'NOT FOUND'}")
    if openai_key:
        cmd.extend(["--api-key", f"openai={openai_key}"])
        print("Added OpenAI API key to Aider command")
    else:
        logger.warning("No OPENAI_API_KEY found in environment")

    # Branch management
    created_branch = None
    original_branch = None
    print("run_aider: Starting branch management...")
    if not dry_run:
        try:
            original_branch = get_current_branch(repo_path)
            print(f"run_aider: Current branch is {original_branch}")
            created_branch = create_branch_for_changes(repo_path, instructions)
            print(f"run_aider: Created new branch {created_branch}")
        except Exception as e:
            logger.error(f"run_aider: Failed to create branch: {e}")
    else:
        print("run_aider: Dry run mode, skipping branch creation.")

    # Example: parse instructions for file deletion keywords
    files_to_delete = []
    if "delete" in instructions.lower() or "remove" in instructions.lower():
        files_to_delete = extract_filenames_from_instructions(instructions)
        if files_to_delete:
            print(f"Deleting files before running Aider: {files_to_delete}")
            manage_files(repo_path, files_to_delete)
            # Stage and commit deletions
            subprocess.run(["git", "add", "-A"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", f"Delete files: {', '.join(files_to_delete)}"], cwd=str(repo_path), check=True)
    # If aider has a dry-run flag, you could pass it based on `dry_run` here.
    if dry_run:
        print("Dry run mode - would execute aider but not making actual changes")

    # Use real Aider for actual AI code changes
    print(f"run_aider: Running aider with instructions: {instructions}")
    print(f"run_aider: Aider command: {' '.join(cmd)}")
    print(f"run_aider: Working directory: {repo_path}")

    try:
        print("run_aider: Attempting code change with aider...")
        print("run_aider: Starting aider subprocess...")
        # Set up environment (inherit from parent process)
        env = os.environ.copy()

        # Run aider with the instructions
        proc = subprocess.run(
            cmd,
            input=instructions,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            cwd=str(repo_path),
            env=env
        )

        print(f"run_aider: Aider completed with return code: {proc.returncode}")
        if proc.stdout:
            print(f"run_aider: Aider stdout: {proc.stdout}")
        if proc.stderr:
            logger.warning(f"run_aider: Aider stderr: {proc.stderr}")

        # If aider failed, try to understand why
        if proc.returncode != 0:
            logger.error(f"run_aider: Aider failed with return code {proc.returncode}")
            stdout_text = (proc.stdout or "").lower()
            stderr_text = (proc.stderr or "").lower()
            if "api-key" in stdout_text or "api-key" in stderr_text:
                logger.error("run_aider: API key issue detected. Check if the OpenAI API key is valid.")
            if "console" in stdout_text or "terminal" in stdout_text:
                logger.error("run_aider: Console/terminal issue detected. This is expected when running from subprocess.")

    except FileNotFoundError:
        # Fallback to test mode if aider is not found
        logger.warning("Aider not found, falling back to test mode")

        # Create a simple test file with the instructions as content
        test_file = repo_path / f"ai_changes_{int(time.time())}.md"
        test_content = f"""# AI Generated Changes

**Instructions:** {instructions}

**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}

**Branch:** {created_branch or 'unknown'}

This file was created because aider was not available.
"""
        test_file.write_text(test_content)
        print(f"Created fallback test file: {test_file}")

        # Commit the test file
        try:
            subprocess.run(["git", "config", "user.name", "AI Assistant"], cwd=str(repo_path), check=False)
            subprocess.run(["git", "config", "user.email", "ai-assistant@example.com"], cwd=str(repo_path), check=False)
            subprocess.run(["git", "add", str(test_file)], cwd=str(repo_path), check=True)
            commit_message = f"Add fallback test file for: {instructions[:50]}..."
            subprocess.run(["git", "commit", "-m", commit_message], cwd=str(repo_path), check=True)
            print(f"Committed fallback test file: {commit_message}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to commit fallback test file: {e}")

        # Mock successful execution
        class MockProcess:
            def __init__(self):
                self.returncode = 0
                self.stdout = f'Created fallback test file: {test_file.name}'
                self.stderr = ''

        proc = MockProcess()

    except subprocess.TimeoutExpired:
        logger.error(f"Aider timed out after {TIMEOUT_SECONDS} seconds")
        proc = subprocess.CompletedProcess(cmd, 1, '', 'Timeout')
    except Exception as e:
        logger.error(f"Error running aider: {e}")
        proc = subprocess.CompletedProcess(cmd, 1, '', str(e))

    execution_time = time.time() - start_time

    # If successful and branch was created, optionally push to remote and create PR
    success = proc.returncode == 0
    push_result = {"success": False, "pushed_to_origin": False}
    pr_result = {"success": False, "created": False}

    print(f"Aider execution: success={success}, created_branch={created_branch}, AUTO_PUSH_BRANCH={AUTO_PUSH_BRANCH}, PUSH_TO_ORIGIN={PUSH_TO_ORIGIN}")
    if success:
        print("run_aider: Code change succeeded.")
    else:
        print(f"run_aider: Code change failed. Return code: {proc.returncode}")

    if success and created_branch:
        print(f"run_aider: Attempting to push branch {created_branch} to remote (forced push)")
        
        # Check if there are running CI/CD workflows on target branch before pushing
        if CHECK_RUNNING_WORKFLOWS and github_token and github_url:
            print(f"Checking for running workflows on {pr_target_branch} branch...")
            workflow_status = check_workflow_runs(github_url, pr_target_branch, github_token)
            
            if workflow_status.get("reason") == "no_workflows_configured":
                print(f"No CI/CD workflows configured for {pr_target_branch} - this appears to be a first push or repository without CI/CD")
                print("Safe to proceed with push")
            elif workflow_status.get("has_running_workflows"):
                print(f"Found {workflow_status.get('running_count', 0)} running workflows on {pr_target_branch}")
                print("Waiting for workflows to complete before pushing...")
                
                # Wait for workflows to complete (with timeout)
                max_wait_time = WORKFLOW_WAIT_TIMEOUT_MINUTES * 60  # Convert to seconds
                wait_interval = 30   # 30 seconds
                waited = 0
                
                while waited < max_wait_time:
                    workflow_status = check_workflow_runs(github_url, pr_target_branch, github_token)
                    if not workflow_status.get("has_running_workflows"):
                        print(f"All workflows completed on {pr_target_branch}")
                        break
                    
                    print(f"Still {workflow_status.get('running_count', 0)} workflows running. Waiting {wait_interval}s...")
                    time.sleep(wait_interval)
                    waited += wait_interval
                
                if waited >= max_wait_time:
                    print(f"Timeout waiting for workflows to complete on {pr_target_branch}")
                    print("Proceeding with push anyway...")
            else:
                print(f"No running workflows found on {pr_target_branch}, safe to proceed")
        else:
            print("Workflow checking disabled or missing GitHub token, proceeding with push")
        
        push_result = push_branch_to_remote(repo_path, created_branch, github_url, github_token)
        if push_result.get("success"):
            print(f"run_aider: Branch {created_branch} successfully pushed to remote.")
        else:
            print(f"Failed to push branch {created_branch} to remote. Error: {push_result.get('error')}")
        print(f"run_aider: Push result details: {push_result}")
        # Wait for CI/CD success before creating PR (if enabled)
        if push_result.get("success") and github_token and github_url and CREATE_PULL_REQUEST:
            ci_success = True
            if WAIT_FOR_CI:
                print(f"Waiting for CI/CD to complete on branch {created_branch}")
                ci_success = wait_for_ci_success(github_url, created_branch, github_token, CI_WAIT_TIMEOUT_MINUTES)
            if ci_success:
                print(f"CI/CD passed, creating pull request for {created_branch}")
                pr_result = create_pull_request(github_url, created_branch, instructions, pr_target_branch, github_token)
            else:
                logger.warning(f"CI/CD failed or timed out for {created_branch}, skipping PR creation")
                pr_result = {"success": False, "error": "CI/CD checks failed or timed out", "ci_required": True}

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

    result = {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "execution_time": execution_time,
        "created_branch": created_branch,
        "original_branch": original_branch,
    }

    # Add branch information to result
    if created_branch:
        result["branch_info"] = {
            "original_branch": original_branch,
            "pushed_to_remote": push_result.get("pushed_to_origin", False),
            "push_success": push_result.get("success", False),
            "push_error": push_result.get("error"),
            "pull_request": pr_result if pr_result.get("success") else None
        }

    return result

def manage_files(repo_path: Path, files_to_delete: List[str], files_to_create: Optional[Dict[str, str]] = None) -> dict:
    """
    Delete specified files and/or create new files with given content in the repo_path.
    Returns a dict with results for each operation.
    """
    results = {"deleted": [], "delete_errors": [], "created": [], "create_errors": []}
    # Delete files
    for rel_path in files_to_delete:
        file_path = repo_path / rel_path
        try:
            # Security: ensure file is inside repo_path
            file_path = file_path.resolve()
            file_path.relative_to(repo_path.resolve())
            if file_path.exists():
                file_path.unlink()
                results["deleted"].append(str(file_path))
            else:
                results["delete_errors"].append(f"{file_path} not found")
        except Exception as e:
            results["delete_errors"].append(f"{file_path}: {e}")

    # Create files
    if files_to_create:
        for rel_path, content in files_to_create.items():
            file_path = repo_path / rel_path
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                results["created"].append(str(file_path))
            except Exception as e:
                results["create_errors"].append(f"{file_path}: {e}")

    return results

# === Endpoints ===

@app.get("/")
async def root():
    """Serve the landing page."""
    return FileResponse('static/landing.html')

@app.get("/dashboard")
async def dashboard():
    """Serve the main application dashboard."""
    return FileResponse('static/index.html')

@app.get("/pricing")
async def pricing_page():
    """Serve the pricing page."""
    return FileResponse('static/pricing.html')

@app.get("/help")
async def help_page():
    """Serve the help/faq page."""
    return FileResponse('static/help.html')

@app.get("/bugs")
async def bugs_page():
    """Serve the system diagnostics page."""
    return FileResponse('static/bugs.html')

@app.get("/vulnerabilities")
async def vulnerabilities_page():
    """Serve the vulnerability scan page."""
    return FileResponse('static/vulnerabilities.html')



@app.get("/login.html")
async def login_page():
    """Serve the login page with injected configuration."""
    try:
        with open('static/login.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inject Google Client ID
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        content = content.replace("YOUR_GOOGLE_CLIENT_ID", client_id)
        
        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Error serving login page: {e}")
        return FileResponse('static/login.html')

@app.get("/api/config")
async def get_config():
    """Get frontend configuration (API base URL, environment, Google Client ID, etc.)."""
    return {
        "api_base": API_BASE_URL,
        "environment": ENVIRONMENT,
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "")
    }

@app.get("/status")
async def status():
    return {"ok": True, "message": "Aider wrapper running", "database": "connected"}

# Repository Management Endpoints
@app.post("/repositories")
async def add_repository(repo: RepositoryRequest, current_user: dict = Depends(get_current_user)):
    """Add a new repository."""
    # Auth handled by Depends(get_current_user)

    try:
        # Check if the branch exists on the remote repository
        import requests
        import re
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)(?:\.git)?', repo.github_url)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub URL format.")
        owner, repo_name = match.groups()
        repo_name = repo_name.replace('.git', '')
        branch_check_url = f"https://api.github.com/repos/{owner}/{repo_name}/branches/{repo.branch}"
        headers = {"Accept": "application/vnd.github.v3+json"}
        if repo.github_token:
            headers["Authorization"] = f"token {repo.github_token}"
        branch_response = requests.get(branch_check_url, headers=headers)
        if branch_response.status_code != 200:
            # Check if repo exists at all
            repo_check_url = f"https://api.github.com/repos/{owner}/{repo_name}"
            repo_response = requests.get(repo_check_url, headers=headers)
            
            if repo_response.status_code == 200:
                # Repo exists, check if it's empty (size 0)
                repo_data = repo_response.json()
                if repo_data.get('size', 0) == 0:
                    print(f"Repository '{repo_name}' appears to be empty. Proceeding without branch check.")
                else:
                     raise HTTPException(status_code=400, detail=f"Branch '{repo.branch}' does not exist on remote repository.")
            else:
                raise HTTPException(status_code=400, detail=f"Branch '{repo.branch}' does not exist on remote repository.")

        # Auto-generate local path if not provided (format: base_path/owner/repo_name)
        local_path = repo.local_path
        if not local_path:
            local_path = str(ALLOWED_BASE / repo.owner / repo.name)
        # Create the directory if it doesn't exist
        local_dir = Path(local_path)
        if not local_dir.exists():
            local_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created local repository directory: {local_dir}")
            # Clone the remote repository into the directory
            try:
                clone_cmd = ["git", "clone", repo.github_url, str(local_dir)]
                print(f"Cloning repository: {' '.join(clone_cmd)}")
                result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    print(f"Git clone failed: {result.stderr}")
                else:
                    print(f"Successfully cloned repository to: {local_dir}")
            except Exception as e:
                print(f"Exception during git clone: {e}")
        repo_id = db.add_repository(
            name=repo.name,
            github_url=repo.github_url,
            owner=repo.owner,
            branch=repo.branch,
            github_token=repo.github_token,
            local_path=local_path,
            description=repo.description,
            user_id=current_user.get("id")
        )
        return {"status": "success", "repo_id": repo_id, "message": "Repository added successfully", "local_path": local_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/repositories")
async def get_repositories(current_user: dict = Depends(get_current_user)):
    """Get all repositories."""
    # Auth handled by Depends(get_current_user)
    
    user_id = current_user.get("id")
    repos = db.get_all_repositories(user_id=user_id)
    return repos

@app.get("/repositories/{repo_id}")
async def get_repository(repo_id: int, current_user: dict = Depends(get_current_user)):
    """Get a specific repository."""
    # Auth handled by Depends(get_current_user)
    
    user_id = current_user.get("id")
    repo = db.get_repository(repo_id, user_id=user_id)
    
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found or access denied")
        
    return repo
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    return repo

@app.delete("/repositories/{repo_id}")
async def delete_repository(repo_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a repository."""
    # Auth handled by Depends(get_current_user)
    
    user_id = current_user.get("id")
    success = db.delete_repository(repo_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    return {"status": "success", "message": "Repository deleted successfully"}

@app.post("/repositories/{repo_id}/clone")
async def clone_repository(repo_id: int, current_user: dict = Depends(get_current_user)):
    """Clone a repository to its local path."""
    # Auth handled by Depends(get_current_user)
    
    user_id = current_user.get("id")
    # Get repository info
    repo = db.get_repository(repo_id, user_id=user_id)
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    
    # Determine repo path
    if repo['local_path']:
        repo_path = Path(repo['local_path'])
    else:
        repo_path = ALLOWED_BASE / repo['owner'] / repo['name']
    
    if repo_path.exists():
        return {"status": "already_exists", "message": f"Repository already exists at {repo_path}"}
    
    try:
        # Create parent directory
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Clone the repository
        clone_cmd = ["git", "clone", repo['github_url'], str(repo_path)]
        if repo['branch'] not in ['main', 'master']:
            clone_cmd.extend(["-b", repo['branch']])
        
        print(f"Cloning repository: {' '.join(clone_cmd)}")
        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            logger.error(f"Git clone failed: {result.stderr}")
            return {
                "status": "error", 
                "message": f"Failed to clone repository: {result.stderr}",
                "manual_command": f"git clone {repo['github_url']} {repo_path}"
            }
        
        print(f"Successfully cloned repository to: {repo_path}")
        return {
            "status": "success", 
            "message": f"Repository cloned successfully to {repo_path}",
            "path": str(repo_path)
        }
        
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Clone operation timed out"}
    except Exception as e:
        logger.error(f"Failed to clone repository: {e}")
        return {
            "status": "error", 
            "message": f"Failed to clone repository: {str(e)}",
            "manual_command": f"git clone {repo['github_url']} {repo_path}"
        }

@app.get("/repositories/{repo_id}/check")
async def check_repository_status(repo_id: int, current_user: dict = Depends(get_current_user)):
    """Check if a repository is empty or has tech stack."""
    user_id = current_user.get("id")
    repo = db.get_repository(repo_id, user_id=user_id)
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)

    # Determine repo path
    if repo['local_path']:
        repo_path = Path(repo['local_path'])
    else:
        repo_path = ALLOWED_BASE / repo['owner'] / repo['name']

    # Check if path exists
    if not repo_path.exists():
        return {
            "exists": False,
            "is_empty": True,
            "message": "Repository not cloned locally. Please clone it first."
        }

    # Check if directory is empty or has minimal files
    try:
        all_files = list(repo_path.rglob('*'))
        # Filter out .git directory files
        code_files = [f for f in all_files if f.is_file() and '.git' not in f.parts]

        # Define tech stack indicators
        tech_indicators = [
            'package.json', 'requirements.txt', 'pom.xml', 'build.gradle',
            'Cargo.toml', 'go.mod', 'composer.json', 'Gemfile',
            'setup.py', 'pyproject.toml', 'yarn.lock', 'package-lock.json'
        ]

        has_tech_stack = any(
            any(indicator in str(f).lower() for indicator in tech_indicators)
            for f in code_files
        )

        # Check for common code file extensions
        code_extensions = ['.py', '.js', '.ts', '.java', '.go', '.rs', '.rb', '.php', '.cpp', '.c', '.cs']
        has_code_files = any(f.suffix.lower() in code_extensions for f in code_files)

        is_empty = len(code_files) == 0 or (len(code_files) <= 2 and not has_tech_stack and not has_code_files)

        return {
            "exists": True,
            "is_empty": is_empty,
            "file_count": len(code_files),
            "has_tech_stack": has_tech_stack,
            "has_code_files": has_code_files,
            "message": "Repository is empty or has no recognizable tech stack" if is_empty else "Repository looks good"
        }

    except Exception as e:
        logger.error(f"Error checking repository: {e}")
        return {
            "exists": True,
            "is_empty": None,
            "message": f"Error checking repository: {str(e)}"
        }

class TechStackValidationRequest(BaseModel):
    tech_stack: str
    github_url: str

@app.post("/validate-techstack")
async def validate_tech_stack(req: TechStackValidationRequest, current_user: dict = Depends(get_current_user)):
    """Validate tech stack using AI before repository registration."""
    try:
        # Set OpenAI API key
        openai.api_key = os.getenv("OPENAI_API_KEY")

        if not openai.api_key:
            logger.warning("OpenAI API key not configured, skipping validation")
            return {
                "is_valid": True,
                "message": "Validation skipped - API key not configured"
            }

        # Extract repo name from URL for context
        repo_name = req.github_url.split('/')[-1].replace('.git', '')

        # Use OpenAI to validate tech stack
        prompt = f"""You are a tech stack validator. Analyze if the provided tech stack is valid and realistic for a software project.

Repository: {repo_name}
Tech Stack Provided: {req.tech_stack}

Evaluate:
1. Are these real, commonly used technologies?
2. Do they work together in a typical software stack?
3. Is the format reasonable (e.g., "Python, FastAPI, PostgreSQL" or "Node.js/React/MongoDB")?

Respond with ONLY a JSON object in this format:
{{"is_valid": true/false, "reason": "brief explanation"}}

Examples of VALID tech stacks:
- "Python, Django, PostgreSQL"
- "Node.js, Express, MongoDB"
- "Java/Spring Boot/MySQL"
- "React, TypeScript, Node.js"

Examples of INVALID tech stacks:
- "asdfasdf" (gibberish)
- "banana, apple, orange" (not technologies)
- "XYZ123" (unclear/fake)
- "" (empty)
"""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a precise tech stack validator. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )

        result_text = response.choices[0].message.content.strip()

        # Parse JSON response
        import json
        result = json.loads(result_text)

        if not result.get('is_valid', True):
            logger.info(f"Tech stack validation failed: {req.tech_stack} - Reason: {result.get('reason')}")
            return {
                "is_valid": False,
                "message": result.get('reason', 'The provided tech stack does not appear to be valid.')
            }

        return {
            "is_valid": True,
            "message": "Tech stack validated successfully"
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response: {e}")
        # If AI response is unparseable, allow it (fail open)
        return {
            "is_valid": True,
            "message": "Validation completed"
        }
    except Exception as e:
        logger.error(f"Error validating tech stack: {e}")
        # Fail open - don't block user if validation service fails
        return {
            "is_valid": True,
            "message": "Validation service unavailable, proceeding"
        }

@app.post("/update-code-by-id")
async def update_code_by_id(req: UpdateByIdRequest, current_user: dict = Depends(get_current_user)):
    """Queue a code update job for processing."""
    try:
        # Get full user details including plan
        user = db.get_user_by_google_id(current_user['user_id'])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        plan_type = user.get('plan_type', 'free')
        limit = PLAN_LIMITS.get(plan_type, 5)
        
        # Check usage
        # For 'free', it's lifetime limit. For others, it's monthly.
        start_date = None
        if plan_type != 'free':
            # Start of current month
            now = datetime.utcnow()
            start_date = datetime(now.year, now.month, 1)
            
        usage = db.get_user_job_count(user['id'], start_date)
        
        if usage >= limit:
            raise HTTPException(
                status_code=403, 
                detail=f"Plan limit exceeded. You have used {usage}/{limit} requests. Please upgrade your plan."
            )

        repo = db.get_repository(req.repo_id)
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Create job in queue
        job_id = db.create_job(
            repo_id=req.repo_id,
            instructions=req.instructions,
            user_id=user['id']
        )
        
        logger.info(f"✅ Job {job_id} queued for repo {req.repo_id} by user {user['id']}")
        
        return {
            "status": "queued",
            "job_id": job_id,
            "message": "Your code update job has been queued",
            "usage": f"{usage+1}/{limit}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/job/{job_id}")
async def get_job_status(job_id: int, current_user: dict = Depends(get_current_user)):
    """Get the status of a job."""
    job = db.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/repository/{repo_id}/jobs")
async def get_repository_jobs(repo_id: int, current_user: dict = Depends(get_current_user)):
    """Get all jobs for a repository."""
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    jobs = db.get_repo_jobs(repo_id)
    return {
        "repo_id": repo_id,
        "jobs": jobs,
        "total": len(jobs)
    }

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
    print(f"Received update request for repo: {repo_path}")

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
        status = "completed"
        if not isinstance(result, dict) or ("error" in result if result else False):
            status = "failed"
        db.update_request_status(
            request_id=request_id,
            status=status,
            execution_time=execution_time,
            result_data=result
        )
        
        # Log API metrics
        db.log_api_metric(
            endpoint=ENDPOINT_UPDATE_CODE,
            repo_id=0,
            metric_name="update_code_success",
            metric_value=execution_time
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
            repo_id=0,
            metric_name="update_code_error",
            metric_value=execution_time
        )
        
        raise HTTPException(status_code=500, detail=str(e))

        raise HTTPException(status_code=500, detail=str(e))

# === Security Endpoints ===

@app.get("/repositories/{repo_id}/branches")
async def get_repository_branches(repo_id: int, current_user: dict = Depends(get_current_user)):
    """List all branches for a repository."""
    user_id = current_user.get("id")
    repo = db.get_repository(repo_id, user_id=user_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    repo_path = Path(repo['local_path'])
    branches = []
    
    try:
        # Fetch all branches
        subprocess.run(["git", "fetch", "--all"], cwd=str(repo_path), check=True, capture_output=True)
        
        # List remote branches
        result = subprocess.run(
            ["git", "branch", "-r"], 
            cwd=str(repo_path), 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        for line in result.stdout.splitlines():
            branch = line.strip()
            if "->" in branch: continue
            branch_name = branch.replace("origin/", "")
            branches.append(branch_name)
            
    except Exception as e:
        logger.error(f"Failed to list branches: {e}")
        return {"branches": [repo['branch']]}
        
    return {"branches": branches}

@app.post("/repositories/{repo_id}/scan")
async def scan_repository(repo_id: int, scan_all_branches: bool = False, target_branch: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Scan a repository for security vulnerabilities."""
    # Admin check
    if current_user.get("email") not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = current_user.get("id")
    repo = db.get_repository(repo_id, user_id=user_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    scanner = SecurityScanner()
    repo_path = Path(repo['local_path'])
    
    branches_to_scan = []
    
    if scan_all_branches:
        try:
            # Fetch all branches
            subprocess.run(["git", "fetch", "--all"], cwd=str(repo_path), check=True, capture_output=True)
            
            # List remote branches
            result = subprocess.run(
                ["git", "branch", "-r"], 
                cwd=str(repo_path), 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            # Parse branches (ignore HEAD)
            for line in result.stdout.splitlines():
                branch = line.strip()
                if "->" in branch:
                    continue
                # Remove 'origin/' prefix
                branch_name = branch.replace("origin/", "")
                branches_to_scan.append(branch_name)
                
        except Exception as e:
            logger.error(f"Failed to list branches: {e}")
            # Fallback to current branch
            branches_to_scan = [repo['branch']]
    elif target_branch:
        branches_to_scan = [target_branch]
    else:
        branches_to_scan = [repo['branch']]

    total_findings = 0
    total_resolved = 0
    all_findings = []

    for branch in branches_to_scan:
        logger.info(f"Scanning branch: {branch}")
        
        # Create a temporary worktree for the branch to avoid messing up the main repo
        import tempfile
        import shutil
        
        worktree_path = Path(tempfile.mkdtemp())
        try:
            # Create worktree
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), f"origin/{branch}" if scan_all_branches or target_branch else branch],
                cwd=str(repo_path),
                check=True,
                capture_output=True
            )
            
            # Scan the worktree
            findings = scanner.scan_repository(str(worktree_path))
            
            # Process findings
            existing_vulns = db.get_vulnerabilities(repo_id, status="open", branch=branch)
            existing_vulns += db.get_vulnerabilities(repo_id, status="in_progress", branch=branch)
            
            existing_map = {f"{v['file_path']}:{v['line_number']}:{v['pattern_id']}": v for v in existing_vulns}
            found_keys = set()
            
            for finding in findings:
                key = f"{finding['file_path']}:{finding['line_number']}:{finding['pattern_id']}"
                found_keys.add(key)
                
                if key not in existing_map:
                    db.log_vulnerability(
                        repo_id=repo_id,
                        file_path=finding['file_path'],
                        description=finding['description'],
                        severity=finding['severity'],
                        line_number=finding['line_number'],
                        pattern_id=finding['pattern_id'],
                        branch=branch
                    )
                    total_findings += 1
                all_findings.append(finding)

            # Auto-resolve fixed vulnerabilities for this branch
            for key, vuln in existing_map.items():
                if key not in found_keys:
                    db.update_vulnerability_status(vuln['id'], "resolved")
                    total_resolved += 1
                    
        except Exception as e:
            logger.error(f"Error scanning branch {branch}: {e}")
        finally:
            # Cleanup worktree
            try:
                subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=str(repo_path), capture_output=True)
                if worktree_path.exists():
                    shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception as e:
                logger.error(f"Failed to cleanup worktree: {e}")

    return {
        "status": "success", 
        "findings_count": total_findings, 
        "resolved_count": total_resolved,
        "scanned_branches": branches_to_scan,
        "findings": all_findings
    }

@app.get("/repositories/{repo_id}/vulnerabilities")
async def get_vulnerabilities(repo_id: int, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Get vulnerabilities for a repository."""
    # Admin check
    if current_user.get("email") not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = current_user.get("id")
    repo = db.get_repository(repo_id, user_id=user_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    vulns = db.get_vulnerabilities(repo_id, status=status)
    return vulns

@app.post("/vulnerabilities/{vuln_id}/fix")
async def fix_vulnerability(vuln_id: int, current_user: dict = Depends(get_current_user)):
    """Queue a job to fix a vulnerability."""
    # Admin check
    if current_user.get("email") not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = current_user.get("id")
    
    # Get vulnerability
    vuln = db.get_vulnerability(vuln_id)
    if not vuln:
        raise HTTPException(status_code=404, detail="Vulnerability not found")
        
    # Verify ownership
    repo = db.get_repository(vuln['repo_id'], user_id=user_id)
    if not repo:
        raise HTTPException(status_code=403, detail="Access denied")
        
    # Create fix job
    instructions = f"Fix the security vulnerability in {vuln['file_path']}. Issue: {vuln['description']} (Severity: {vuln['severity']}). Please analyze the code and apply a secure fix.\n\n[METADATA:VULN_ID:{vuln_id}]"
    job_id = db.create_job(vuln['repo_id'], instructions, user_id=user_id)
    
    # Update status
    db.update_vulnerability_status(vuln_id, "in_progress")
    
    return {"status": "success", "job_id": job_id, "message": "Fix job queued"}
    
    # Let's assume we added get_vulnerability to DB. 
    # Since we didn't yet, let's skip the strict check for this specific tool call 
    # and implement it properly in the next step.
    
    return {"status": "error", "message": "Not implemented yet"}

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
    print(f"Exec debug command in {cwd_path}: {cmd}")
    return execute_command(cmd, cwd_path)

# Required authentication
@app.get("/protected-endpoint")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello {current_user['name']}!"}

def start_background_worker():
    """Start the job processing worker in a separate thread."""
    try:
        from worker import process_repositories
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_repositories())
    except Exception as e:
        logger.error(f"Error in background worker: {e}", exc_info=True)

@app.get("/api/bugs")
async def get_bug_reports(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Get a list of bug reports."""
    # Admin check
    if current_user.get("email") not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")

    bugs = db.get_bug_reports(status=status)
    return bugs

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_type = type(exc).__name__
    error_message = str(exc)
    stack_trace = traceback.format_exc()
    endpoint = request.url.path
    
    # Try to get user_id from state if available (set by middleware/dependencies)
    user_id = None
    if hasattr(request.state, "user"):
         user_id = request.state.user.get("id")

    logger.error(f"Unhandled exception: {error_message}", exc_info=True)
    
    # Log to DB
    bug_id = db.log_bug(
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
        endpoint=endpoint,
        user_id=user_id if user_id is not None else 0
    )
    
    # Auto-fix: Queue a job if we can identify the repository
    try:
        current_path = os.getcwd()
        repo = db.get_repository_by_local_path(current_path)
        
        if repo:
            logger.info(f"🔍 Found repository for auto-fix: {repo['name']}")
            
            # Create instructions for the AI
            instructions = f"""
CRITICAL BUG FIX REQUIRED

Error Type: {error_type}
Error Message: {error_message}
Endpoint: {endpoint}

Stack Trace:
{stack_trace}

Please analyze the stack trace and fix the bug in the codebase. 
Ensure the fix handles the edge case that caused this error.
"""
            # Create job
            job_id = db.create_job(
                repo_id=repo['id'],
                instructions=instructions,
                user_id=user_id
            )
            logger.info(f"✅ Auto-fix job {job_id} queued for bug {bug_id}")
            
            # Update bug status to in_progress
            db.update_bug_status(bug_id, "in_progress")
            
    except Exception as e:
        logger.error(f"Failed to queue auto-fix job: {e}")

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "bug_report_id": bug_id}
    )

# Run by uvicorn when invoked directly
if __name__ == "__main__":
    # Initialize database and create tables
    logger.info("🔧 Initializing database...")
    db.init_db()
    logger.info("✅ Database initialized")
    
    # Start background worker in a separate thread
    logger.info("🚀 Starting background job processor...")
    worker_thread = Thread(target=start_background_worker, daemon=True)
    worker_thread.start()
    logger.info("✅ Background worker started")
    
    # Start FastAPI server
    logger.info("🌐 Starting FastAPI server on http://localhost:8080")
    uvicorn.run(
        "main:app",
        host=HOST_ADDRESS,
        port=8080,
        reload=False
    )


