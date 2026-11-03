"""Administra exclusivamente el PostgreSQL de desarrollo de esta carpeta."""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
DATA = LOCAL / "pgdata"
BIN = ROOT / ".runtime" / "pgsql" / "bin"


def run_pg(program, *args, check=True):
    executable = BIN / f"{program}.exe"
    if not executable.exists():
        raise RuntimeError("Falta PostgreSQL local. Ejecuta scripts/install-postgres.ps1.")
    return subprocess.run(
        [str(executable), *map(str, args)],
        check=check,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def environment():
    path = ROOT / ".env"
    if not path.exists():
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "POSTGRES_ADMIN_PASSWORD"):
            content = content.replace(f"{key}=\n", f"{key}={secrets.token_urlsafe(48)}\n")
        # El modo exclusivo evita sobrescribir una configuracion existente.
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        print("Configuracion local creada en .env; secretos no mostrados.")
    values = dotenv_values(path)
    for key in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "POSTGRES_ADMIN_PASSWORD"):
        if not values.get(key):
            raise RuntimeError(f"Falta {key} en .env.")
    if (
        values.get("POSTGRES_HOST") != "127.0.0.1"
        or values.get("POSTGRES_DB") != "sicfe_dev"
        or values.get("POSTGRES_USER") != "sicfe_app"
    ):
        raise RuntimeError("Este comando solo administra la base local sicfe_dev / sicfe_app.")
    port = int(values.get("POSTGRES_PORT", "5433"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("Puerto local no valido.")
    LOCAL.mkdir(exist_ok=True)
    return values


def start(values):
    if not (DATA / "PG_VERSION").exists():
        raise RuntimeError("Base sin inicializar. Ejecuta setup.ps1.")
    if run_pg("pg_ctl", "-D", DATA, "status", check=False).returncode == 0:
        return
    run_pg(
        "pg_ctl",
        "-D",
        DATA,
        "-l",
        LOCAL / "postgres.log",
        "-o",
        f"-h 127.0.0.1 -p {int(values['POSTGRES_PORT'])}",
        "-w",
        "start",
    )


def setup(values):
    if not (DATA / "PG_VERSION").exists():
        password_file = LOCAL / f"init-{secrets.token_hex(8)}.tmp"
        try:
            password_file.write_text(values["POSTGRES_ADMIN_PASSWORD"], encoding="utf-8")
            run_pg(
                "initdb",
                "-D",
                DATA,
                "-U",
                "sicfe_admin",
                "--encoding=UTF8",
                "--locale=C",
                "--auth-host=scram-sha-256",
                "--auth-local=scram-sha-256",
                f"--pwfile={password_file}",
            )
        finally:
            password_file.unlink(missing_ok=True)
    start(values)
    with psycopg.connect(
        host="127.0.0.1",
        port=int(values["POSTGRES_PORT"]),
        dbname="postgres",
        user="sicfe_admin",
        password=values["POSTGRES_ADMIN_PASSWORD"],
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'sicfe_app'").fetchone():
            conn.execute(
                sql.SQL(
                    "CREATE ROLE sicfe_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Literal(values["POSTGRES_PASSWORD"]))
            )
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'sicfe_dev'").fetchone():
            conn.execute("CREATE DATABASE sicfe_dev OWNER sicfe_app")
    print("PostgreSQL local listo. La aplicacion usa una cuenta sin privilegios de superusuario.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "start", "stop", "status"])
    command = parser.parse_args().command
    values = environment()
    if command == "setup":
        setup(values)
    elif command == "start":
        start(values)
    elif command == "stop":
        if run_pg("pg_ctl", "-D", DATA, "status", check=False).returncode == 0:
            run_pg("pg_ctl", "-D", DATA, "-m", "fast", "-w", "stop")
    else:
        sys.exit(run_pg("pg_ctl", "-D", DATA, "status", check=False).returncode)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except psycopg.Error:
        print(
            "No se pudo configurar PostgreSQL. Revisa .env y .local/postgres.log.", file=sys.stderr
        )
        sys.exit(1)
