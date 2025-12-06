# Security Configuration

## Environment Variables

All sensitive configuration must be loaded from environment variables, never hardcoded in the codebase.

### Local Development (.env)

1. **Create `.env` file from template:**
```bash
cp .env.example .env
```

2. **Generate a strong API key for local dev:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

3. **Update `.env` with your values:**
```env
AIDER_API_KEY=your_generated_key_here
OPENAI_API_KEY=sk-your_key_here
```

4. **NEVER commit `.env` to git** - it's in `.gitignore` for a reason

### Production Deployment

For production environments, set variables directly:

- **GitHub Actions / CI/CD:** Use Secrets in repository settings
- **Docker:** Pass as environment variables or use secret management services
- **Cloud Platforms:**
  - AWS: Use AWS Secrets Manager
  - Azure: Use Azure Key Vault
  - GCP: Use Secret Manager
  - Heroku: Use Config Vars

Example for GitHub Actions:
```yaml
env:
  AIDER_API_KEY: ${{ secrets.AIDER_API_KEY }}
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Key Configuration Variables

| Variable | Purpose | Local Dev | Production |
|----------|---------|-----------|------------|
| `AIDER_API_KEY` | Backend API authentication | Generate random 32-char string | Use Secrets Manager |
| `OPENAI_API_KEY` | OpenAI API for Aider | From OpenAI Platform | Use Secrets Manager |
| `GOOGLE_CLIENT_ID` | OAuth client ID | Optional for local dev | Use Secrets Manager |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | Optional for local dev | Use Secrets Manager |
| `DATABASE_URL` | Database connection | SQLite OK for dev | Use production DB |

## Frontend Authentication

- ✅ NO API keys in frontend code
- ✅ Frontend uses cookies (`credentials: 'include'`)
- ✅ Backend validates requests with environment variables
- ✅ Sensitive data never exposed in browser console/source

## API Security

- All endpoints require Bearer token authentication
- Token is validated server-side against `AIDER_API_KEY` from environment
- GitHub tokens stored in database are encrypted
- Secrets never logged or exposed in error messages

## Best Practices

1. **Rotate keys regularly** in production
2. **Use strong random generation** for all keys
3. **Audit access** to secret management systems
4. **Monitor logs** for unauthorized access attempts
5. **Use HTTPS only** in production
6. **Implement rate limiting** on API endpoints
7. **Keep dependencies updated** for security patches
