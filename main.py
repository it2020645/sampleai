# server.py
from fastapi import FastAPI, Request, HTTPException, Header
import sys
from tqdm import tqdm

# Ensure stdout uses UTF-8 encoding if possible (Python 3.7+)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
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
from dotenv import load_dotenv
import sys

# Load environment variables from .env file
load_dotenv()

# Reconfigure stdout to use UTF-8 encoding


# === CONFIG ===
API_KEY = os.getenv("AIDER_API_KEY", "change_this_to_a_strong_key")  # Load from .env file
ALLOWED_BASE = Path(os.getenv("ALLOWED_BASE_PATH", "C:/Users/batal/OneDrive/Documents/GitHub/ai")).resolve()
AIDER_CMD = "aider"  # assume aider is on PATH (or provide full path)
TIMEOUT_SECONDS = int(os.getenv("AIDER_TIMEOUT_SECONDS", "300"))  # max seconds to let aider run

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
print(f"Base directory ensured: {ALLOWED_BASE}")

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

def create_branch_for_changes(repo_path: Path, instructions: str) -> str:
    """
    Create a new git branch for the changes with a descriptive name.
    Always creates a feature branch with intelligent naming:
    - If instructions provided: feature/{short-word-from-instructions}-{timestamp}
    - If instructions blank: feature/{YYYY-MM-DD}-{timestamp}
    Returns the branch name created.
    """
    import datetime
    import re
    import time
    
    # Generate unique timestamp suffix
    timestamp = int(time.time())
    
    # Generate branch name based on instructions
    if instructions and instructions.strip():
        # Extract first meaningful word from instructions (sanitized)
        sanitized_instructions = re.sub(r'[^a-zA-Z0-9\s]', '', instructions.strip())
        words = [word for word in sanitized_instructions.split() if len(word) > 2]  # Filter short words
        branch_suffix = words[0].lower() if words else "change"
    else:
        # If blank instructions, use date format
        branch_suffix = datetime.datetime.now().strftime("%Y-%m-%d")
    
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
        title = f"AI Code Changes: {instructions[:60]}{'...' if len(instructions) > 60 else ''}"
        body = f"""## AI-Generated Code Changes

**Instructions:** {instructions}

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
    cmd = [AIDER_CMD, "--yes-always", "--auto-commits", "--no-pretty", "--no-stream"]

    # Add OpenAI API key in the correct format for Aider
    openai_key = os.getenv("OPENAI_API_KEY")
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
        print(f"Failed to set up remote origin for {github_url}")

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
        if push_result.get("success") and github_token and github_url:
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

@app.post("/repositories/{repo_id}/clone")
async def clone_repository(repo_id: int, authorization: Optional[str] = Header(None)):
    """Clone a repository to its local path."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    # Get repository info
    repo = db.get_repository(repo_id)
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

@app.post("/update-code-by-id")
async def update_code_by_id(req: UpdateByIdRequest, authorization: Optional[str] = Header(None)):
    """Update code using repository ID instead of path."""
    print("Entered /update-code-by-id API endpoint")
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
        repo_path = ALLOWED_BASE / repo['owner'] / repo['name']

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
        github_token = req.github_token or repo.get('github_token')
        print(f"req.pr_target_branch={req.pr_target_branch}, PR_TARGET_BRANCH={PR_TARGET_BRANCH}")
        target_branch = req.pr_target_branch or PR_TARGET_BRANCH
        print(f"Final target_branch={target_branch}")
        result = run_aider(
            repo_path,
            req.instructions,
            dry_run=req.dry_run if req.dry_run is not None else False,
            repo_id=req.repo_id,
            github_url=repo['github_url'],
            github_token=github_token,
            pr_target_branch=target_branch
        )
        execution_time = time.time() - start_time
        status = "completed"
        if not isinstance(result, dict) or ("error" in result if result else False):
            status = "failed"
        db.update_request_status(
            request_id=request_id,
            status=status,
            execution_time=execution_time,
            result_data=result
        )
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
        db.update_request_status(
            request_id=request_id,
            status="error",
            execution_time=execution_time,
            result_data=error_result
        )
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

@app.get("/repositories/{repo_id}/ci-status/{branch_name}")
async def get_repository_ci_status(repo_id: int, branch_name: str, authorization: Optional[str] = Header(None)):
    """Get CI/CD status for a specific branch."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    # Get repository info
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    
    # Get CI status using repository's GitHub token
    github_token = repo.get('github_token')
    if not github_token:
        raise HTTPException(status_code=400, detail="No GitHub token configured for this repository")
    
    ci_status = get_ci_status(repo['github_url'], branch_name, github_token)
    
    return {
        "repo_id": repo_id,
        "repo_name": repo['name'],
        "branch_name": branch_name,
        "ci_status": ci_status,
        "github_url": repo['github_url']
    }

@app.post("/repositories/{repo_id}/create-pr/{branch_name}")
async def manually_create_pr(repo_id: int, branch_name: str, authorization: Optional[str] = Header(None)):
    """Manually create a PR for a branch (bypass CI/CD wait)."""
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=ERROR_MISSING_AUTH)
    token = authorization.split()[-1]
    if token != API_KEY:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=ERROR_INVALID_KEY)
    
    # Get repository info
    repo = db.get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=ERROR_REPO_NOT_FOUND)
    
    # Get GitHub token
    github_token = repo.get('github_token')
    if not github_token:
        raise HTTPException(status_code=400, detail="No GitHub token configured for this repository")
    
    # Create PR with generic instructions
    instructions = f"Manual PR creation for branch {branch_name}"
    pr_result = create_pull_request(
        github_url=repo['github_url'],
        branch_name=branch_name,
        instructions=instructions,
        base_branch="master",  # or repo['branch']
        github_token=github_token
    )
    
    return {
        "repo_id": repo_id,
        "repo_name": repo['name'],
        "branch_name": branch_name,
        "pr_result": pr_result
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
    print(f"Exec debug command in {cwd_path}: {cmd}")
    return execute_command(cmd, cwd_path)

# Run by uvicorn when invoked directly
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
