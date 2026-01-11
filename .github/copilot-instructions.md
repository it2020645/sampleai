# Aider API Server - AI Development Guide

## Architecture Overview

This is a **FastAPI-based AI code automation server** that wraps the [Aider](https://github.com/paul-gauthier/aider) CLI tool. It executes AI-guided code changes on Git repositories via HTTP API with GitHub integration, user authentication, and comprehensive execution logging.

**Core Services:**
- **FastAPI Web Server** (`main.py`): REST API + web UI for repository management and code execution
- **PostgreSQL Database** (`database.py`, `models.py`): User auth, job queue, execution logs, repositories
- **Aider Wrapper** (`run_aider()` in `main.py`): Orchestrates aider CLI with branch creation, git operations, CI waiting
- **Job Worker** (`worker.py`): Async background processor for queued jobs (not yet fully integrated)
- **Security Scanner** (`security_scanner.py`): Static analysis for hardcoded secrets, SQL injection, dangerous patterns
- **OAuth2 Auth** (`auth.py`, `auth_routes.py`): Google OAuth2 + JWT token-based API authentication

## Critical Data Flows

**Code Execution Flow:**
1. User sends POST `/update-code-by-id` with repo ID + instructions
2. Server validates user owns repo, checks plan limits (`PLAN_LIMITS` dict)
3. If `AUTO_CREATE_BRANCH=true`: Creates `feature/aider-<semantic-name>-<timestamp>` branch
4. Calls `run_aider(repo_path, instructions)` → spawns aider subprocess
5. Aider edits files, commits changes to branch
6. If `AUTO_PUSH_BRANCH=true`: Pushes branch + optionally creates PR via GitHub API
7. Logs execution to `aider_execution_logs` table with stdout/stderr/returncode
8. Returns result to client with branch info, push status, PR link

**GitHub Integration:** When pushing, auto-detects GitHub URL from `.git/config` origin or accepts explicit `github_url` parameter. Uses GitHub token for API calls (PR creation, CI status polling).

**Plan Limits Enforcement:** Jobs checked against `PLAN_LIMITS['free'|'pro'|'enterprise']` - free plan allows 5 jobs, pro 25, enterprise 1000.

## Key Files & Patterns

| File | Purpose | Key Patterns |
|------|---------|--------------|
| [main.py](main.py#L1) | API server & aider orchestration | Pydantic request models, error handling via HTTPException, git subprocess calls |
| [database.py](database.py#L1) | SQLAlchemy ORM wrapper | Single `RDBMS` class with session-per-method, `to_dict()` for serialization |
| [models.py](models.py#L1) | SQLAlchemy table definitions | Declarative base, foreign keys (User → Job, Repository), timestamps |
| [auth.py](auth.py#L1) | Google OAuth2 + JWT | Mini JWT fallback if PyJWT unavailable, Google ID token verification |
| [worker.py](worker.py#L1) | Background job processor | Async processing loop, imports `run_aider` to avoid circular deps |

**Environment Config:**
- `DATABASE_URL`: PostgreSQL connection string (required)
- `ALLOWED_BASE_PATH`: Base directory for cloning repos (default: `C:/Users/batal/OneDrive/Documents/GitHub/ai`)
- `AIDER_TIMEOUT_SECONDS`: Max runtime for aider (default: 300s)
- `AUTO_CREATE_BRANCH`, `AUTO_PUSH_BRANCH`, `PUSH_TO_ORIGIN`: Git workflow flags
- `CREATE_PULL_REQUEST`, `PR_TARGET_BRANCH`: GitHub PR automation
- `WAIT_FOR_CI`, `CI_WAIT_TIMEOUT_MINUTES`: CI polling after push

## Developer Workflows

**Running Locally:**
```bash
# 1. Set up environment
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure .env with DATABASE_URL, GOOGLE_CLIENT_ID/SECRET, etc.
cp .env.example .env

# 3. Start server
python main.py  # Runs on http://localhost:8000

# 4. Open web UI at http://localhost:8000/login
```

**Running Tests:**
```bash
pytest tests/                          # All tests
pytest tests/test_system.py -v         # System integration tests
pytest tests/test_github_integration.py -v  # GitHub-specific tests
```

**Database Debugging:**
```bash
# Check schema and tables
python dbcheck.py  # or dbfix.py for schema repairs
python cleanup_db.py  # Reset for testing
```

**Aider CLI Directly** (for manual testing):
```bash
aider --model claude-3-5-sonnet path/to/repo --message "your instructions"
```

## Code Patterns to Preserve

1. **Session Management**: Always use `db.get_session()` in RDBMS methods, never share sessions across threads
2. **Error Responses**: Use FastAPI `HTTPException(status_code=401, detail="message")` not raw dicts
3. **Dependency Injection**: Use `Depends(get_current_user)` for auth, returns user dict
4. **Subprocess Safety**: Quote arguments in `run_aider()` with `shlex.quote()`, never pass unsanitized repo paths
5. **Branch Naming**: Use `generate_semantic_name(instructions)` + timestamp to create unique, descriptive branch names
6. **Git Operations**: All git commands wrapped in subprocess calls; check returncode before trusting output
7. **Logging**: Use Python `logging` module (not print), structured with timestamps for audit trail

## Common Modifications

**Adding a New API Endpoint:**
```python
# In main.py, add near other endpoints
@app.post("/your-endpoint")
async def your_endpoint(request: YourRequest, current_user: dict = Depends(get_current_user)):
    # Check permissions: if not current_user["is_admin"]: raise HTTPException(403)
    # Return JSONResponse with result
    return JSONResponse({"status": "success", "data": {...}})
```

**Adding Database Fields:**
1. Add column to model class in [models.py](models.py)
2. Add migration method to RDBMS in [database.py](database.py)
3. Run migration script (e.g., `python add_plan_column.py` as reference)

**Integrating New Git Provider** (not just GitHub):
- Extend `create_pull_request()` to detect provider from URL
- Add provider-specific API calls (similar to GitHub REST API pattern in [main.py#L518](main.py#L518))

## Testing Strategy

**Unit Tests** (`tests/`): Test individual functions in isolation (e.g., `test_connection.py` for DB)
**Integration Tests**: `test_github_integration.py` mocks GitHub API; `test_system.py` runs end-to-end
**Mocking Pattern**: Use `pytest-mock` to patch subprocess calls and HTTP requests

## Critical Known Issues & TODOs

- **Job Queue Not Active**: `worker.py` exists but job queue processing isn't wired to main loop (see [worker.py#L20](worker.py#L20))
- **Token Encryption**: GitHub tokens stored in plaintext in DB (prod should use encrypted columns)
- **Aider Version**: Pinned to 0.2.6 in `requirements.txt`; newer versions may have API changes
- **Error Handling**: Some git operations have fallback logic but don't always propagate errors to user clearly

## Security Checklist

- ✅ API key validation on all endpoints (via `AIDER_API_KEY` env var)
- ✅ OAuth2 + JWT token expiration enforcement
- ✅ SQL injection prevention (using SQLAlchemy ORM, not string queries)
- ⚠️ GitHub tokens not encrypted (consider KMS in production)
- ⚠️ No rate limiting (add if exposed to untrusted clients)
- ⚠️ Static analysis in `security_scanner.py` is basic regex (not true AST-based analysis)
