"""Run Python code for the model, in a throwaway Docker container (default) or locally with uv.

Based on gpt-oss's python_docker tool (Apache 2.0, (c) OpenAI); a time limit was added.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile

IMAGE = "python:3.11"
TIME_LIMIT = 60  # seconds
_docker_client = None


class PythonToolError(Exception):
    pass


def run_in_docker(code: str) -> str:
    global _docker_client
    try:
        import docker
    except ImportError as e:
        raise PythonToolError("The docker package is missing. Install with: pip install 'tora-ai[python]'") from e
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
            try:
                _docker_client.images.get(IMAGE)
            except docker.errors.ImageNotFound:
                _docker_client.images.pull(IMAGE)
        except docker.errors.DockerException as e:
            _docker_client = None
            raise PythonToolError(f"Docker is not available ({e}). Start Docker Desktop, or set TORA_PYTHON_BACKEND=uv.") from e

    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        data = code.encode("utf-8")
        info = tarfile.TarInfo(name="script.py"); info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    container = _docker_client.containers.create(IMAGE, command="sleep infinity", detach=True, network_disabled=True)
    try:
        container.start()
        container.put_archive(path="/tmp", data=archive.getvalue())
        result = container.exec_run(f"timeout {TIME_LIMIT} python /tmp/script.py")
        output = result.output.decode("utf-8", errors="replace")
        if result.exit_code == 124:
            output += f"\n[Stopped: exceeded the {TIME_LIMIT}s time limit]"
    finally:
        container.remove(force=True)
    return output


def run_with_uv(code: str) -> str:
    # Runs on this computer with no sandbox: only for code you trust.
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "script.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            # Pin the interpreter to this one, so a stray .python-version file can't pick another.
            version = f"{sys.version_info.major}.{sys.version_info.minor}"
            result = subprocess.run(["uv", "run", "--no-project", "--python", version, "python", path],
                                    capture_output=True, text=True, timeout=TIME_LIMIT, cwd=tmp)
        except FileNotFoundError as e:
            raise PythonToolError("uv is not installed or not on PATH.") from e
        except subprocess.TimeoutExpired:
            return f"[Stopped: exceeded the {TIME_LIMIT}s time limit]"
    return result.stdout + (("\n" + result.stderr) if result.stderr else "")


def run_python(code: str, backend: str = "docker") -> str:
    if backend == "docker":
        output = run_in_docker(code)
    elif backend == "uv":
        output = run_with_uv(code)
    else:
        raise PythonToolError(f"Unknown TORA_PYTHON_BACKEND {backend!r}; use 'docker' or 'uv'.")
    return output if output.strip() else "[No output. Use print() to show results.]"
