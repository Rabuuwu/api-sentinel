"""Own PostgreSQL cluster + API + worker, all on this machine. No global installs."""

import os
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local"
PGDATA = STATE / "postgres"
PORT = 54329
PYTHON = ROOT / ".venv/bin/python"


def command(args, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def tools():
    for name in ("initdb", "pg_ctl", "createdb", "psql"):
        if not shutil.which(name):
            raise RuntimeError(f"Missing {name}; add PostgreSQL 17+ bin directory to PATH")


def start_db():
    running = (
        subprocess.run(
            ["pg_ctl", "-D", str(PGDATA), "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    if not running:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", PORT)) == 0:
                raise RuntimeError(f"Port {PORT} is occupied; existing service was not modified")
        command(
            [
                "pg_ctl",
                "-D",
                PGDATA,
                "-l",
                STATE / "postgres.log",
                "-o",
                f"-h 127.0.0.1 -p {PORT} -k {shlex.quote(str(STATE))}",
                "-w",
                "start",
            ]
        )
    return not running


def stop_db():
    command(["pg_ctl", "-D", PGDATA, "-m", "fast", "-w", "stop"])


def prepare():
    tools()
    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE.chmod(0o700)
    if not PYTHON.exists():
        command([sys.executable, "-m", "venv", ROOT / ".venv"])
    command([PYTHON, "-m", "pip", "install", "-e", ".[dev]"])
    if not shutil.which("npm"):
        raise RuntimeError("Node.js 24 and npm are required to build the React dashboard")
    command(["npm", "install", "--prefix", "frontend"])
    command(["npm", "run", "build", "--prefix", "frontend"])
    envfile = ROOT / ".env"
    if not envfile.exists():
        password = secrets.token_urlsafe(32)
        content = (
            f"DATABASE_URL=postgresql+asyncpg://sentinel:{password}@127.0.0.1:{PORT}/sentinel\n"
            f"POSTGRES_PASSWORD={password}\nSENTINEL_API_KEY={secrets.token_urlsafe(40)}\n"
            "DISCORD_WEBHOOK_URL=\n"
        )
        fd = os.open(envfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(content)
    command([PYTHON, ROOT / "scripts/prepare_database.py", "--validate-only"])
    if not (PGDATA / "PG_VERSION").exists():
        # Read through the project's dependency; never print the secret.
        result = command(
            [
                PYTHON,
                "-c",
                "from dotenv import dotenv_values; "
                "print(dotenv_values('.env').get('POSTGRES_PASSWORD', ''))",
            ],
            capture_output=True,
            text=True,
        )
        password = result.stdout.strip()
        if not password or password == "change-me":
            raise RuntimeError("Set a random POSTGRES_PASSWORD in .env before setup")
        password_file = STATE / "init-password"
        fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as output:
                output.write(password + "\n")
            command(
                [
                    "initdb",
                    "-D",
                    PGDATA,
                    "-U",
                    "sentinel",
                    "--auth=scram-sha-256",
                    "--pwfile",
                    password_file,
                    "--encoding=UTF8",
                    "--locale=C",
                ]
            )
        finally:
            password_file.unlink(missing_ok=True)
    started = start_db()
    try:
        command([PYTHON, ROOT / "scripts/prepare_database.py"])
    finally:
        if started:
            stop_db()
    print("Ready. Run: python3 scripts/local.py run")


def run():
    tools()
    if not (PGDATA / "PG_VERSION").exists():
        raise RuntimeError("Run python3 scripts/local.py setup first")
    command([PYTHON, ROOT / "scripts/prepare_database.py", "--validate-only"])
    if not (ROOT / "frontend/dist/index.html").exists():
        raise RuntimeError(
            "Build the dashboard first: npm install --prefix frontend "
            "&& npm run build --prefix frontend"
        )
    started = start_db()
    children = []
    try:
        command([ROOT / ".venv/bin/alembic", "upgrade", "head"])
        for args in (
            [
                "-m",
                "uvicorn",
                "api_sentinel.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            ["-m", "api_sentinel.worker"],
        ):
            children.append(subprocess.Popen([str(PYTHON), *args], cwd=ROOT))
        print(
            "Panel: http://127.0.0.1:8000 | API key: local .env | Ctrl+C stops services", flush=True
        )
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A service stopped; see its output above")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=45)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if started:
            stop_db()


if __name__ == "__main__":
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "help"
        if action == "setup":
            prepare()
        elif action == "run":
            run()
        else:
            print("Usage: python3 scripts/local.py setup|run")
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Local setup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
