from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.security import assert_startup_security


def log(message: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with (LOG_DIR / "facai-agent-watchdog.log").open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/app", timeout=8) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def run_powershell(script: str) -> None:
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def stop_port_listeners(port: int) -> None:
    script = (
        f"$listeners = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -Unique; "
        "foreach ($listener in $listeners) { "
        "if ($listener) { Stop-Process -Id $listener -Force -ErrorAction SilentlyContinue } "
        "}"
    )
    run_powershell(script)


def stop_legacy_servers(target_port: int) -> None:
    legacy_ports = [8010, 8011, 8012, 8013, 8014, 8015]
    for port in legacy_ports:
        if port != target_port:
            stop_port_listeners(port)


def start_server(port: int) -> subprocess.Popen:
    bind_host = "0.0.0.0"
    assert_startup_security(bind_host)
    LOG_DIR.mkdir(exist_ok=True)
    stdout = (LOG_DIR / "facai-agent-server.out.log").open("a", encoding="utf-8")
    stderr = (LOG_DIR / "facai-agent-server.err.log").open("a", encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        bind_host,
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=stdout,
        stderr=stderr,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    log(f"Started server process {process.pid} on port {port}")
    return process


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()

    log(f"Service monitor started for {ROOT} on port {args.port}")
    stop_legacy_servers(args.port)

    process: subprocess.Popen | None = None
    while True:
        process_running = process is not None and process.poll() is None
        if not process_running and not healthy(args.port):
            stop_port_listeners(args.port)
            time.sleep(2)
            process = start_server(args.port)
            time.sleep(8)
        elif process_running and not healthy(args.port):
            log("Health check failed; restarting server")
            stop_port_listeners(args.port)
            time.sleep(2)
            process = start_server(args.port)
            time.sleep(8)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
