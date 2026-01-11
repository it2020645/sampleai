# Environment Configuration Setup

## Quick Setup

### 1. **Create and Activate Virtual Environment**

**Windows (PowerShell):**
```bash
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\Activate.ps1

# If you get execution policy error, run:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Windows (Command Prompt):**
```bash
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. **Install Dependencies**

```bash
# Make sure venv is activated (should see (.venv) in your prompt)
pip install -r requirements.txt
```

### 3. **Copy the example environment file:**
```bash
cp .env.example .env
```

### 4. **Generate a secure API key:**
```bash
python -c "import secrets; print('sk-aider-proj-' + secrets.token_urlsafe(32))"
```

### 5. **Update your `.env` file** with the generated key:
```env
AIDER_API_KEY=sk-aider-proj-YOUR_GENERATED_KEY_HERE
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AIDER_API_KEY` | API key for FastAPI server authentication | `change_this_to_a_strong_key` |
| `ALLOWED_BASE_PATH` | Base directory for repositories | `C:/Users/batal/OneDrive/Documents/GitHub/ai` |
| `AIDER_TIMEOUT_SECONDS` | Maximum seconds for aider execution | `300` |
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `GOOGLE_CLIENT_ID` | Google OAuth2 Client ID | Required for login |
| `GOOGLE_CLIENT_SECRET` | Google OAuth2 Client Secret | Required for login |

## Security Notes

- ✅ The `.env` file is automatically ignored by git
- ✅ Never commit API keys to version control
- ✅ Use the `.env.example` file as a template for new deployments
- ✅ API keys are loaded at runtime from environment variables

## Deactivating Virtual Environment

When done working:
```bash
deactivate
```

## Usage

The application will automatically load variables from the `.env` file when it starts. If the `.env` file doesn't exist or a variable is missing, it will fall back to the default values defined in the code.

To use different environment files:
```bash
# Load from a specific env file (macOS/Linux)
export $(cat .env.production | xargs) && python main.py

# Windows PowerShell
Get-Content .env.production | ForEach-Object { $_ -match '^([^=]+)=(.*)' | Out-Null; [Environment]::SetEnvironmentVariable($matches[1], $matches[2]) }; python main.py
```
