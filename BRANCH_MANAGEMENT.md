# Git Branch Management System

## Overview
Your aider system now automatically creates new branches for code changes, providing better version control and change tracking.

## Configuration (.env file)
```env
# Git Branch Management
AUTO_CREATE_BRANCH=true          # Automatically create branches for changes
BRANCH_PREFIX=aider-changes       # Prefix for auto-generated branch names  
AUTO_PUSH_BRANCH=false          # Automatically push branches to remote
```

## How It Works

### 1. **Automatic Branch Creation**
When `AUTO_CREATE_BRANCH=true`, the system:
- Creates a descriptive branch name: `aider-changes-{description}-{timestamp}`
- Example: `aider-changes-add-new-function-20250908-143022`
- Switches to the new branch before making changes
- Keeps track of the original branch

### 2. **Branch Naming Convention**
- **Prefix**: Configurable via `BRANCH_PREFIX` (default: `aider-changes`)
- **Description**: First 3 words from instructions (sanitized)
- **Timestamp**: `YYYYMMDD-HHMMSS` format for uniqueness
- **Full format**: `{prefix}-{description}-{timestamp}`

### 3. **Frontend Control**
Users can control branch creation per request:
- ✅ **"Create new branch for changes"** checkbox (checked by default)
- Can override the global `AUTO_CREATE_BRANCH` setting
- Works alongside the existing "Dry Run" option

### 4. **Response Information**
After successful execution, you get:
```json
{
  "status": "done",
  "result": {
    "returncode": 0,
    "branch_info": {
      "created_branch": "aider-changes-add-login-20250908-143022",
      "original_branch": "main",
      "pushed_to_remote": false
    }
  }
}
```

## Benefits

### ✅ **Change Isolation**
- Each set of changes gets its own branch
- No risk of conflicts with main development
- Easy to review changes before merging

### ✅ **Traceability** 
- Clear branch names show what changes were made
- Timestamps help track when changes occurred
- Original branch is preserved for easy rollback

### ✅ **Collaboration**
- Branches can be pushed to remote for team review
- Pull requests can be created from generated branches
- Changes don't interfere with ongoing work

### ✅ **Flexible Control**
- Global setting via environment variable
- Per-request override via web interface
- Dry run mode bypasses branch creation

## Usage Examples

### Example 1: Simple Feature Addition
**Request**: "Add a login function to the authentication module"
**Generated Branch**: `aider-changes-add-login-function-20250908-143022`

### Example 2: Bug Fix
**Request**: "Fix null pointer exception in user validation"  
**Generated Branch**: `aider-changes-fix-null-pointer-20250908-143155`

### Example 3: Refactoring
**Request**: "Refactor database connection logic for better performance"
**Generated Branch**: `aider-changes-refactor-database-connection-20250908-143301`

## Configuration Options

| Setting | Values | Description |
|---------|--------|-------------|
| `AUTO_CREATE_BRANCH` | `true`/`false` | Enable automatic branch creation |
| `BRANCH_PREFIX` | string | Prefix for branch names |
| `AUTO_PUSH_BRANCH` | `true`/`false` | Push branches to remote automatically |

## Manual Override
Users can disable branch creation for specific requests by unchecking the "Create new branch for changes" option in the web interface, even if `AUTO_CREATE_BRANCH=true` globally.

## Remote Push (Optional)
Set `AUTO_PUSH_BRANCH=true` to automatically push created branches to the remote repository, enabling immediate collaboration and backup.
