import requests
import json

login_data = {"username": "engineer@sovereign.local", "password": __import__("os").getenv("TEST_ENGINEER_PASSWORD", "")}
r_auth = requests.post("http://localhost:8000/api/auth/login", data=login_data)
if r_auth.status_code != 200:
    print("Auth failed:", r_auth.text)
    exit(1)

token = r_auth.json().get("access_token")

headers = {"Authorization": f"Bearer {token}"}

# Test 1: Simple Print
print("--- Test 1: Simple execution ---")
payload = {
    "tool_name": "run_code",
    "args": {"code": "print('Hello from sandbox!')"}
}
r_test = requests.post("http://localhost:8000/api/agent/test-tool", json=payload, headers=headers)
print(json.dumps(r_test.json(), indent=2))

# Test 2: Network Isolation (should fail)
print("\n--- Test 2: Network isolation ---")
payload = {
    "tool_name": "run_code",
    "args": {"code": "import urllib.request\ntry:\n  urllib.request.urlopen('http://google.com', timeout=2)\n  print('SUCCESS')\nexcept Exception as e:\n  print(f'FAILED: {e}')"}
}
r_test = requests.post("http://localhost:8000/api/agent/test-tool", json=payload, headers=headers)
print(json.dumps(r_test.json(), indent=2))

# Test 3: Timeout
print("\n--- Test 3: Timeout ---")
payload = {
    "tool_name": "run_code",
    "args": {"code": "import time\ntime.sleep(15)\nprint('Done')"}
}
r_test = requests.post("http://localhost:8000/api/agent/test-tool", json=payload, headers=headers)
print(json.dumps(r_test.json(), indent=2))

