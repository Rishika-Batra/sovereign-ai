import requests
import json

base_url = "http://localhost/api"
# base_url = "http://localhost:8000/api" # If running from host, wait, inside workspace we can hit localhost directly if NGINX is on 80.
# NGINX is exposed on localhost? The script runs on the host. Let's try 8000 first (backend).

def test_agent():
    # Login
    resp = requests.post(
        "http://localhost/api/auth/login",
        json={"email": "employee@example.com", "password": "employee_pass"}
    )
    if resp.status_code != 200:
        print("Login failed:", resp.status_code, resp.text)
        return
    token = resp.json().get("access_token")
    print("Logged in!")

    # Run agent
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"variables": {"target": "Compressor"}}
    
    resp = requests.post(f"http://localhost/api/agents/1/run", headers=headers, json=payload)
    print("Status:", resp.status_code)
    print("Response:", resp.text)

test_agent()
