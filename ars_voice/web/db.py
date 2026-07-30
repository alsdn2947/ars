"""SQLite 저장소. 표준 라이브러리 sqlite3만 사용한다.

토큰은 원문을 저장하지 않고 SHA-256 해시만 저장한다. 접속 링크가
곧 자격 증명이므로, DB가 유출되어도 링크를 복원할 수 없게 한다.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'editor',        -- 'admin' | 'editor'
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    user_id INTEGER NOT NULL REFERENCES users(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    UNIQUE(user_id, project_id)
);
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    max_uses INTEGER NOT NULL DEFAULT 10,
    used INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ments (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    options TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS renders (
    id INTEGER PRIMARY KEY,
    ment_id INTEGER NOT NULL REFERENCES ments(id),
    status TEXT NOT NULL DEFAULT 'queued',      -- queued | running | done | error
    file_name TEXT,
    error TEXT,
    requested_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(24)


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)


# ── 사용자/인증 ──────────────────────────────────────────────


def create_user(db_path, name: str, role: str = "editor") -> tuple[int, str]:
    """사용자를 만들고 (id, 접속 토큰 원문)을 돌려준다."""
    token = new_token()
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO users (name, role, token_hash, created_at) VALUES (?,?,?,?)",
            (name, role, hash_token(token), now_iso()),
        )
        return cur.lastrowid, token


def get_user_by_token(db_path, token: str) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE token_hash=?", (hash_token(token),)
        ).fetchone()


def ensure_admin(db_path) -> str | None:
    """관리자가 없으면 만들고 접속 토큰을 돌려준다(이미 있으면 None)."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone()
    if row:
        return None
    _, token = create_user(db_path, "관리자", role="admin")
    return token


def reset_admin(db_path) -> str:
    """새 관리자 토큰을 재발급한다 (기존 관리자 토큰은 무효화)."""
    token = new_token()
    with connect(db_path) as conn:
        row = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        if row:
            conn.execute("UPDATE users SET token_hash=? WHERE id=?", (hash_token(token), row["id"]))
        else:
            conn.execute(
                "INSERT INTO users (name, role, token_hash, created_at) VALUES (?,?,?,?)",
                ("관리자", "admin", hash_token(token), now_iso()),
            )
    return token


# ── 프로젝트/멤버십 ──────────────────────────────────────────


def create_project(db_path, name: str) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, created_at) VALUES (?,?)", (name, now_iso())
        )
        return cur.lastrowid


def list_projects_for(db_path, user: sqlite3.Row) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        if user["role"] == "admin":
            return conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return conn.execute(
            """SELECT p.* FROM projects p
               JOIN memberships m ON m.project_id = p.id
               WHERE m.user_id=? ORDER BY p.id""",
            (user["id"],),
        ).fetchall()


def user_can_access(db_path, user: sqlite3.Row, project_id: int) -> bool:
    if user["role"] == "admin":
        with connect(db_path) as conn:
            return conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is not None
    with connect(db_path) as conn:
        return (
            conn.execute(
                "SELECT 1 FROM memberships WHERE user_id=? AND project_id=?",
                (user["id"], project_id),
            ).fetchone()
            is not None
        )


def add_membership(db_path, user_id: int, project_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO memberships (user_id, project_id) VALUES (?,?)",
            (user_id, project_id),
        )


def list_members(db_path, project_id: int) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return conn.execute(
            """SELECT u.id, u.name, u.role, u.created_at FROM users u
               JOIN memberships m ON m.user_id = u.id
               WHERE m.project_id=? ORDER BY u.id""",
            (project_id,),
        ).fetchall()


# ── 초대 ─────────────────────────────────────────────────────


def create_invite(db_path, project_id: int, max_uses: int = 10, expires_days: int = 14) -> str:
    token = new_token()
    expires = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat(timespec="seconds")
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO invites (token_hash, project_id, max_uses, expires_at, created_at) VALUES (?,?,?,?,?)",
            (hash_token(token), project_id, max_uses, expires, now_iso()),
        )
    return token


def get_valid_invite(db_path, token: str) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM invites WHERE token_hash=?", (hash_token(token),)
        ).fetchone()
    if row is None:
        return None
    if row["used"] >= row["max_uses"]:
        return None
    if row["expires_at"] < now_iso():
        return None
    return row


def redeem_invite(db_path, invite_id: int, name: str) -> tuple[int, str]:
    """초대를 사용해 편집자 계정을 만들고 (user_id, 개인 토큰)을 돌려준다."""
    with connect(db_path) as conn:
        invite = conn.execute("SELECT * FROM invites WHERE id=?", (invite_id,)).fetchone()
        if invite is None or invite["used"] >= invite["max_uses"]:
            raise ValueError("유효하지 않은 초대입니다.")
        token = new_token()
        cur = conn.execute(
            "INSERT INTO users (name, role, token_hash, created_at) VALUES (?,?,?,?)",
            (name, "editor", hash_token(token), now_iso()),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO memberships (user_id, project_id) VALUES (?,?)",
            (user_id, invite["project_id"]),
        )
        conn.execute("UPDATE invites SET used=used+1 WHERE id=?", (invite_id,))
        return user_id, token


# ── 멘트 ─────────────────────────────────────────────────────


def create_ment(db_path, project_id: int, title: str, body: str, options: str, by: str) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO ments (project_id, title, body, options, updated_at, updated_by) VALUES (?,?,?,?,?,?)",
            (project_id, title, body, options, now_iso(), by),
        )
        return cur.lastrowid


def update_ment(db_path, ment_id: int, title: str, body: str, options: str, by: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE ments SET title=?, body=?, options=?, updated_at=?, updated_by=? WHERE id=?",
            (title, body, options, now_iso(), by, ment_id),
        )


def get_ment(db_path, ment_id: int) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM ments WHERE id=?", (ment_id,)).fetchone()


def list_ments(db_path, project_id: int) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM ments WHERE project_id=? ORDER BY id DESC", (project_id,)
        ).fetchall()


def delete_ment(db_path, ment_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM renders WHERE ment_id=?", (ment_id,))
        conn.execute("DELETE FROM ments WHERE id=?", (ment_id,))


# ── 렌더링 ───────────────────────────────────────────────────


def create_render(db_path, ment_id: int, by: str) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO renders (ment_id, status, requested_by, created_at) VALUES (?,?,?,?)",
            (ment_id, "queued", by, now_iso()),
        )
        return cur.lastrowid


def update_render(db_path, render_id: int, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    with connect(db_path) as conn:
        conn.execute(f"UPDATE renders SET {sets} WHERE id=?", (*fields.values(), render_id))


def get_render(db_path, render_id: int) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM renders WHERE id=?", (render_id,)).fetchone()


def list_renders(db_path, ment_id: int, limit: int = 20) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM renders WHERE ment_id=? ORDER BY id DESC LIMIT ?",
            (ment_id, limit),
        ).fetchall()
