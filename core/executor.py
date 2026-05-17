"""Command and script executor."""
import subprocess
import sys
import os
import tempfile

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run_shell(command: str) -> tuple[str, int]:
    """Run a shell command, return (output, returncode)."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=30, creationflags=_NO_WINDOW
        )
        output = result.stdout + (result.stderr or "")
        return output, result.returncode
    except subprocess.TimeoutExpired:
        return "⚠ Timeout (30s)", 1
    except Exception as e:
        return str(e), 1


def run_python(code: str, timeout: int = 10) -> str:
    """Run Python code in a subprocess, return stdout+stderr."""
    with tempfile.NamedTemporaryFile(
        suffix=".py", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        path = tmp.name
    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_NO_WINDOW
        )
        return result.stdout + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return f"⚠ Timeout ({timeout}s)"
    except Exception as e:
        return str(e)
    finally:
        os.unlink(path)
