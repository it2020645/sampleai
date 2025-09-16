# Database Usage Guide

## Overview

I've created a very lightweight SQLite database for your Aider API server that tracks:

- **Request Logs**: All API requests with their parameters and results
- **Aider Executions**: Detailed logs of aider command executions  
- **API Metrics**: Performance metrics for monitoring

## Database Features

### Tables Created:
1. `request_logs` - API request tracking
2. `aider_executions` - Aider command execution logs
3. `api_metrics` - Performance monitoring

### New API Endpoints:

- `GET /logs` - Get recent API request logs
- `GET /repo/{repo_name}/history` - Get execution history for a repository
- `GET /stats` - Get API usage statistics
- `DELETE /logs/cleanup` - Clean up old logs

## Usage Examples

### 1. Run the server with database
```bash
python main.py
```

### 2. Test the database
```bash
python test_database.py
```

### 3. Check logs via API
```bash
curl -H "Authorization: Bearer your_api_key" http://localhost:8000/logs
```

### 4. Get statistics
```bash
curl -H "Authorization: Bearer your_api_key" http://localhost:8000/stats
```

### 5. Clean up old logs (older than 30 days)
```bash
curl -X DELETE -H "Authorization: Bearer your_api_key" http://localhost:8000/logs/cleanup?days=30
```

## Database File

The database is stored as `aider_api.db` in your project directory. It's a single SQLite file that contains all your data.

## Configuration

Update these values in `main.py` before running:
- `API_KEY` - Change to a strong API key
- `ALLOWED_BASE` - Set to your repositories base directory

## Benefits

✅ **Lightweight**: Single SQLite file, no external database needed  
✅ **Fast**: Optimized queries with proper indexing  
✅ **Logging**: Complete audit trail of all operations  
✅ **Monitoring**: Performance metrics and usage stats  
✅ **Cleanup**: Automatic old data cleanup  
✅ **Zero Config**: Works out of the box  

The database automatically initializes when you start the server and begins logging all operations!
