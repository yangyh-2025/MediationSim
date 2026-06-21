#!/usr/bin/env python
"""
偏见调停多智能体模拟系统 — 一键启动脚本

用法: python run.py

只需 .env 中有 API 密钥，一键启动后端 + 前端 + 自动打开浏览器。
Ctrl+C 优雅停止所有服务。
"""
from __future__ import annotations

import os
import sys
import time
import signal
import subprocess
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# ── 加载 .env ──
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
VENV_DIR = PROJECT_ROOT / ".venv"
BACKEND_PORT = 59870
FRONTEND_PORT = 59871

_backend_proc: subprocess.Popen | None = None
_frontend_proc: subprocess.Popen | None = None


def find_venv_python() -> str | None:
    for candidate in [
        VENV_DIR / "Scripts" / "python.exe",
        VENV_DIR / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def verify_deps(python_exe: str) -> bool:
    """Quick check that all core deps are importable."""
    try:
        subprocess.run(
            [python_exe, "-c",
             "import fastapi, uvicorn, openai, pydantic; print('deps ok')"],
            capture_output=True, text=True, timeout=30,
        )
        return True
    except Exception:
        return False


def kill_port(port: int) -> None:
    import platform
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        else:
            subprocess.run(
                ["lsof", "-ti", f":{port}", "|", "xargs", "kill", "-9"],
                shell=True, capture_output=True,
            )
    except Exception:
        pass


def start_backend(python_exe: str) -> subprocess.Popen:
    banner("启动后端 (端口 59870)")
    kill_port(BACKEND_PORT)
    return subprocess.Popen(
        [python_exe, "-m", "uvicorn", "backend.main:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--reload"],
        cwd=str(PROJECT_ROOT),
    )


def start_frontend() -> subprocess.Popen:
    banner("启动前端 (端口 59871)")
    kill_port(FRONTEND_PORT)
    return subprocess.Popen(
        ["npx", "vite", "--port", str(FRONTEND_PORT)],
        cwd=str(FRONTEND_DIR),
        shell=(os.name == "nt"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def cleanup(*args) -> None:
    print("\n")
    if _frontend_proc:
        banner("停止前端")
        _frontend_proc.terminate()
        try: _frontend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired: _frontend_proc.kill()
    if _backend_proc:
        banner("停止后端")
        _backend_proc.terminate()
        try: _backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired: _backend_proc.kill()
    kill_port(BACKEND_PORT)
    kill_port(FRONTEND_PORT)
    print("\n  系统已停止。\n")


def banner(msg: str) -> None:
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}")


def check_api_key() -> bool:
    if os.getenv("OPENAI_API_KEY"):
        return True

    env_file = PROJECT_ROOT / ".env"
    env_template = PROJECT_ROOT / ".env.example"

    banner("配置 API 密钥")
    print()

    if not env_file.exists():
        import shutil
        shutil.copy(env_template, env_file)
        print(f"  已创建 {env_file.name}，请编辑填入 OPENAI_API_KEY")
    else:
        print(f"  {env_file.name} 中的 OPENAI_API_KEY 为空")

    print(f"\n  文件位置: {env_file}")
    print("\n  是否继续启动（API 功能不可用）？(y/n)")
    if input("  > ").strip().lower() != "y":
        print("  已取消。")
        return False
    return True


def main() -> None:
    banner("偏见调停多智能体模拟系统 v1.0")

    python_exe = find_venv_python()
    if not python_exe:
        print("\n  错误：未找到虚拟环境 .venv")
        print("  请先运行: python -m venv .venv")
        print("  然后: .venv\\Scripts\\pip install -r backend/requirements.txt")
        sys.exit(1)

    print(f"  Python: {python_exe}")

    if not verify_deps(python_exe):
        print("  警告：依赖不完整，尝试安装...")
        subprocess.run(
            [python_exe, "-m", "pip", "install", "--proxy",
             os.getenv("HTTP_PROXY", ""),
             "-r", str(BACKEND_DIR / "requirements.txt")],
            cwd=str(PROJECT_ROOT), timeout=300,
        )

    if not (FRONTEND_DIR / "node_modules").exists():
        print("  前端依赖未安装，正在安装...")
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), timeout=300)

    if not check_api_key():
        sys.exit(0)

    global _backend_proc
    _backend_proc = start_backend(python_exe)

    print("  等待后端就绪...", end="", flush=True)
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{BACKEND_PORT}/api/health", timeout=1)
            print(" OK"); break
        except Exception:
            time.sleep(0.8); print(".", end="", flush=True)
    else:
        print("\n  警告：后端启动超时")

    global _frontend_proc
    _frontend_proc = start_frontend()

    print("  等待前端就绪...", end="", flush=True)
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{FRONTEND_PORT}", timeout=1)
            print(" OK"); break
        except Exception:
            time.sleep(0.8); print(".", end="", flush=True)
    else:
        print("\n  警告：前端启动超时")

    frontend_url = f"http://localhost:{FRONTEND_PORT}"
    backend_url = f"http://localhost:{BACKEND_PORT}"
    print(f"\n  后端:  {backend_url}\n  前端:  {frontend_url}\n  API:   {backend_url}/docs\n")
    print("  按 Ctrl+C 停止所有服务\n")

    try:
        webbrowser.open(frontend_url)
    except Exception:
        pass

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
