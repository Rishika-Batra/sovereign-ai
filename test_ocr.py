import requests
import json
import sys

login_data = {"username": "admin@sovereign.local", "password": __import__("os").getenv("TEST_ADMIN_PASSWORD", "")}
r_auth = requests.post("http://localhost:8000/api/auth/login", data=login_data)
if r_auth.status_code != 200:
    print("Auth failed:", r_auth.text)
    sys.exit(1)

token = r_auth.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

with open("/tmp/fake_scan.pdf", "rb") as f:
    files = {"file": ("fake_scan.pdf", f, "application/pdf")}
    r_upload = requests.post("http://localhost:8000/api/documents/upload", headers=headers, files=files)
    
print(json.dumps(r_upload.json(), indent=2))
