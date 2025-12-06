import os
import subprocess
from dotenv import load_dotenv

load_dotenv(override=True)

key = os.getenv("OPENAI_API_KEY")
if not key:
    print("ERROR: OPENAI_API_KEY not found in .env")
else:
    print(f"Found key: {key[:10]}...")

print("Running aider check...")
try:
    # Try a simple version check with the key passed explicitly
    cmd = ["aider", "--version"]
    env = os.environ.copy()
    # env["OPENAI_API_KEY"] = key # load_dotenv sets this in os.environ
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    print(f"Version check return code: {result.returncode}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")

    # Try a dry run with a dummy message to check auth
    # We use --no-git to avoid git operations for this test if possible, but aider is git-centric.
    # We'll just try to list models or something that requires auth if possible, 
    # but aider doesn't have a 'check-auth' command.
    # We will try to run a simple message.
    
    print("\nAttempting to run aider with a simple message (dry run)...")
    cmd = ["aider", "--model", "gpt-4o", "--message", "Hello", "--no-git", "--exit"]
    # We need to pass the key explicitly as main.py does
    cmd.extend(["--api-key", f"openai={key}"])
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    print(f"Run return code: {result.returncode}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")
    
except Exception as e:
    print(f"Exception: {e}")
