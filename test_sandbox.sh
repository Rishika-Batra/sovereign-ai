TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -d "username=admin@sovereign.local&password=${TEST_ADMIN_PASSWORD}" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "--- Test 1 ---"
curl -s -X POST http://localhost:8000/api/agent/test-tool -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"tool_name": "run_code", "args": {"code": "print(\"Hello from sandbox!\")"}}'

echo -e "\n--- Test 2 ---"
curl -s -X POST http://localhost:8000/api/agent/test-tool -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"tool_name": "run_code", "args": {"code": "import urllib.request\ntry:\n  urllib.request.urlopen(\"http://google.com\", timeout=2)\n  print(\"SUCCESS\")\nexcept Exception as e:\n  print(f\"FAILED: {e}\")"}}'

echo -e "\n--- Test 3 ---"
curl -s -X POST http://localhost:8000/api/agent/test-tool -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"tool_name": "run_code", "args": {"code": "import time\ntime.sleep(15)\nprint(\"Done\")"}}'
echo ""
