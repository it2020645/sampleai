# Environment Configuration Setup

## Quick Setup

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Generate a secure API key:**
   ```bash
   python -c "import secrets; print('sk-aider-proj-' + secrets.token_urlsafe(32))"
   ```

3. **Update your `.env` file** with the generated key:
   ```env
   AIDER_API_KEY=sk-aider-proj-YOUR_GENERATED_KEY_HERE
   ```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AIDER_API_KEY` | API key for FastAPI server authentication | `change_this_to_a_strong_key` |
| `ALLOWED_BASE_PATH` | Base directory for repositories | `C:/Users/batal/OneDrive/Documents/GitHub/ai` |
| `AIDER_TIMEOUT_SECONDS` | Maximum seconds for aider execution | `300` |
| `DATABASE_PATH` | SQLite database file path | `aider_api.db` |

## Security Notes

- ✅ The `.env` file is automatically ignored by git
- ✅ Never commit API keys to version control
- ✅ Use the `.env.example` file as a template for new deployments
- ✅ API keys are loaded at runtime from environment variables

## Usage

The application will automatically load variables from the `.env` file when it starts. If the `.env` file doesn't exist or a variable is missing, it will fall back to the default values defined in the code.

To use different environment files:
```bash
# Load from a specific env file
export $(cat .env.production | xargs) && python main.py
```
