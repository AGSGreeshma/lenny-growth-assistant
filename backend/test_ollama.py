import requests

url = "http://localhost:11434/api/generate"

payload = {
    "model": "llama3.1",
    "prompt": "Say hello in one short sentence.",
    "stream": False
}

response = requests.post(url, json=payload, timeout=180)

print("Status:", response.status_code)
print("Response:", response.text)