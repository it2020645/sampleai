import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("No API key found in .env")
    exit(1)

print(f"Testing API Key: {api_key[:10]}...{api_key[-4:]}")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Test with gpt-4
data = {
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 5
}

print("\nAttempting request to OpenAI API (gpt-4)...")
try:
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Success! Key is valid and has quota.")
    else:
        print("Error response:")
        print(response.text)
except Exception as e:
    print(f"Request failed: {e}")
