from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

DB_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = DB_DIR / "easyvpn.db"
DB_PATH = Path(os.getenv("EASYVPN_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()

DEFAULT_USER = {"username": "admin", "password": "easyvpn"}


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS servers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                region TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                username TEXT NOT NULL,
                status TEXT NOT NULL,
                ssh_private_key TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS clients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS privileges (
                name TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS user_privileges (
                username TEXT NOT NULL,
                privilege_name TEXT NOT NULL,
                PRIMARY KEY (username, privilege_name),
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY (privilege_name) REFERENCES privileges(name) ON DELETE CASCADE
            );
            """
        )

        # For older DBs created before is_admin existed.
        if not _column_exists(conn, "users", "is_admin"):
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))"
            )

        # For older DBs created before ssh_private_key existed.
        if not _column_exists(conn, "servers", "ssh_private_key"):
            conn.execute("ALTER TABLE servers ADD COLUMN ssh_private_key TEXT NOT NULL DEFAULT ''")

        conn.execute(
            "INSERT OR IGNORE INTO users (username, password, is_admin) VALUES (?, ?, ?)",
            (DEFAULT_USER["username"], DEFAULT_USER["password"], 1),
        )
        conn.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (DEFAULT_USER["username"],))

        # Remove old demo rows that were seeded by previous versions.
        conn.execute("DELETE FROM servers WHERE id IN ('sg-1', 'de-1', 'us-1')")
        conn.execute("DELETE FROM clients WHERE id IN ('00', '01', '02')")


def fetch_servers() -> list[dict[str, str]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, region, ip_address, username, status FROM servers ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def add_server(
    name: str,
    region: str,
    ip_address: str,
    username: str,
    status: str,
    ssh_private_key: str,
) -> str:
    server_id = f"srv-{uuid4().hex[:8]}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO servers (id, name, region, ip_address, username, status, ssh_private_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (server_id, name, region, ip_address, username, status, ssh_private_key),
        )
    return server_id


def set_server_ssh_private_key(server_id: str, ssh_private_key: str) -> None:
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE servers SET ssh_private_key = ? WHERE id = ?",
            (ssh_private_key, server_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Server '{server_id}' does not exist")


def get_server_ssh_private_key(server_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ssh_private_key FROM servers WHERE id = ?",
            (server_id,),
        ).fetchone()
    return row["ssh_private_key"] if row is not None else None


def fetch_clients() -> list[dict[str, str]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, status FROM clients ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def verify_user(username: str, password: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE username = ? AND password = ?",
            (username, password),
        ).fetchone()
    return row is not None


def user_exists(username: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT username FROM users WHERE username = ?", (username,)).fetchone()
    return row is not None


def is_admin_user(username: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE username = ?", (username,)).fetchone()
    return bool(row["is_admin"]) if row is not None else False


def add_privilege(name: str) -> bool:
    normalized = name.strip()
    if not normalized:
        return False

    with get_connection() as conn:
        cursor = conn.execute("INSERT OR IGNORE INTO privileges (name) VALUES (?)", (normalized,))
    return cursor.rowcount > 0


def list_privileges() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM privileges ORDER BY name").fetchall()
    return [row["name"] for row in rows]


def set_user_privileges(username: str, privilege_names: list[str]) -> None:
    normalized = sorted({name.strip() for name in privilege_names if name.strip()})

    with get_connection() as conn:
        user_row = conn.execute("SELECT username FROM users WHERE username = ?", (username,)).fetchone()
        if user_row is None:
            raise ValueError(f"User '{username}' does not exist")

        for name in normalized:
            conn.execute("INSERT OR IGNORE INTO privileges (name) VALUES (?)", (name,))

        conn.execute("DELETE FROM user_privileges WHERE username = ?", (username,))
        conn.executemany(
            "INSERT INTO user_privileges (username, privilege_name) VALUES (?, ?)",
            [(username, name) for name in normalized],
        )


def get_user_privileges(username: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT privilege_name
            FROM user_privileges
            WHERE username = ?
            ORDER BY privilege_name
            """,
            (username,),
        ).fetchall()
    return [row["privilege_name"] for row in rows]


def get_user_access(username: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        user = conn.execute(
            "SELECT username, is_admin FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if user is None:
            return None

        privileges = conn.execute(
            """
            SELECT privilege_name
            FROM user_privileges
            WHERE username = ?
            ORDER BY privilege_name
            """,
            (username,),
        ).fetchall()

    return {
        "username": user["username"],
        "is_admin": bool(user["is_admin"]),
        "privileges": [row["privilege_name"] for row in privileges],
    }
