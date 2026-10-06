import subprocess

def run_in_sandbox(code: str, timeout: int = 10) -> dict:
    """
    Passes code via stdin to a secure docker container without network access,
    and returns the stdout/stderr.
    """
    cmd = [
        "docker", "run", "-i", "--rm", 
        "--network=none", 
        "--memory=256m", 
        "--cpus=0.5",
        "python:3.11-slim",
        "python", "-"
    ]
    
    try:
        result = subprocess.run(
            cmd,
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "timed_out": False
        }
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode('utf-8') if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else (e.stderr or "")
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": 124,  # standard timeout exit code
            "timed_out": True
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
            "timed_out": False
        }
