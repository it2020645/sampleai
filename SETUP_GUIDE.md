# Configuration for Aider Repository Manager

## Setup Instructions

1. **Update Configuration in main.py:**
   ```python
   API_KEY = "your-super-secure-api-key-here"  # Change this!
   ALLOWED_BASE = Path("C:/Users/batal/OneDrive/Documents/GitHub").resolve()  # Update to your repos folder
   ```

2. **Start the Server:**
   ```bash
   python main.py
   ```

3. **Open the Frontend:**
   Navigate to: http://localhost:8000

## Features

### 🗄️ **Enhanced Database**
- Stores GitHub repository information (URL, owner, branch, token)
- Links operations to specific repositories by ID
- Complete audit trail of all changes

### 🌐 **Frontend Interface**
- Add repositories with GitHub URL, branch, and token
- Select repositories by ID instead of file paths
- Execute code changes through a beautiful web interface
- View execution results in real-time

### 🚀 **New API Endpoints**

#### Repository Management:
- `POST /repositories` - Add a new repository
- `GET /repositories` - List all repositories  
- `GET /repositories/{id}` - Get specific repository
- `DELETE /repositories/{id}` - Delete repository

#### Code Execution:
- `POST /update-code-by-id` - Execute changes using repository ID

#### Existing Endpoints:
- `GET /status` - Health check
- `GET /logs` - Request logs
- `GET /stats` - Usage statistics
- `DELETE /logs/cleanup` - Clean old logs

## Usage Example

### 1. Add Repository via Frontend:
- Name: "sampleai"
- GitHub URL: "https://github.com/it2020645/sampleai"
- Owner: "it2020645"
- Branch: "feature-ai"
- Token: (optional, for private repos)

### 2. Execute Changes:
- Select repository from dropdown
- Enter instructions: "Add a function to calculate factorial"
- Click "Execute Changes"

### 3. View Results:
- See real-time execution output
- Check logs and statistics
- Monitor performance metrics

## Benefits

✅ **ID-Based Operations**: No more file path management  
✅ **GitHub Integration**: Store repository metadata  
✅ **Beautiful UI**: Easy-to-use web interface  
✅ **Enhanced Logging**: Complete operation tracking  
✅ **Secure**: API key authentication  
✅ **Scalable**: Support for multiple repositories  

## Security Notes

- Change the default API_KEY before deploying
- GitHub tokens are stored in the database (consider encryption for production)
- All operations require API key authentication
- Repository access is restricted to ALLOWED_BASE directory

The system is now ready for production use with a complete frontend and enhanced database!
