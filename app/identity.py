"""Service identities and shared credentials, separate from every user's data export."""
import base64
import hashlib
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app import database
from app.auth import hash_password, verify_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'member')),
    active INTEGER NOT NULL DEFAULT 1,
    session_version INTEGER NOT NULL DEFAULT 0,
    data_slot TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS invitations (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used_by TEXT REFERENCES users(id),
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL, month TEXT NOT NULL,
    provider TEXT NOT NULL, model TEXT, kind TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_shared_usage_month ON api_usage(month, user_id);
"""


def store_path() -> Path:
    return database.DB_PATH.with_name(database.DB_PATH.stem + '-identity.db')


def init_store():
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('xb'):
            pass
    path.chmod(0o600)
    with connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connection():
    # Never silently recreate a missing identity store in a live request.
    conn = sqlite3.connect(store_path().resolve().as_uri() + '?mode=rw', uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def has_users() -> bool:
    with connection() as conn:
        return conn.execute('SELECT 1 FROM users LIMIT 1').fetchone() is not None


def get_user(user_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    return dict(row) if row else None


def legacy_user() -> dict | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE data_slot='legacy'").fetchone()
    return dict(row) if row else None


def public_user(user: dict) -> dict:
    return {key: user[key] for key in ('id', 'username', 'role', 'active', 'created_at')}


def data_path(user: dict) -> Path:
    slot = user['data_slot']
    if slot == 'legacy':
        return database.DB_PATH
    if not re.fullmatch(r'[a-f0-9]{32}', slot):
        raise ValueError('Invalid internal data slot')
    return database.DB_PATH.parent / (database.DB_PATH.stem + '-users') / slot / 'shiome.db'


def normalized_username(username: str) -> str:
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}', username):
        raise ValueError('用户名需为 3–32 位字母、数字、下划线、点或短横线')
    return username


def password_digest(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError('密码需为 12–128 个字符')
    return hash_password(password)


def _cipher(secret: str) -> Fernet:
    material = hashlib.sha256(('shiome-model-key-v1:' + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def shared_api_key() -> str | None:
    encrypted = None
    if store_path().exists():
        with connection() as conn:
            encrypted = conn.execute("SELECT value FROM settings WHERE name='anthropic_key'").fetchone()
    if encrypted:
        from app.main import AUTH
        try:
            return _cipher(AUTH.secret).decrypt(encrypted['value'].encode()).decode()
        except InvalidToken:
            raise ValueError('模型密钥无法解密，请管理员重新保存密钥') from None
    return (os.environ.get('ANTHROPIC_API_KEY') or '').strip() or None


def key_configured() -> bool:
    if store_path().exists():
        with connection() as conn:
            if conn.execute("SELECT 1 FROM settings WHERE name='anthropic_key'").fetchone():
                return True
    return bool((os.environ.get('ANTHROPIC_API_KEY') or '').strip())


def _save_key(conn, key: str, secret: str):
    encrypted = _cipher(secret).encrypt(key.encode()).decode()
    conn.execute("INSERT INTO settings(name,value) VALUES ('anthropic_key',?) "
                 'ON CONFLICT(name) DO UPDATE SET value=excluded.value', (encrypted,))


def save_key(key: str, secret: str):
    with connection() as conn:
        _save_key(conn, key, secret)


def create_owner(username: str, password: str, secret: str, api_key: str | None = None) -> dict:
    username, digest = normalized_username(username), password_digest(password)
    user_id = secrets.token_hex(16)
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise ValueError('管理员账号已创建，请直接登录')
        conn.execute('INSERT INTO users(id,username,password_hash,role,data_slot,created_at) '
                     "VALUES (?,?,?,'admin','legacy',?)", (user_id, username, digest, int(time.time())))
        if api_key:
            _save_key(conn, api_key, secret)
        # Existing personal data stays at its original path; prior costs join the shared budget.
        with database.database_scope(database.DB_PATH), database.get_conn() as original:
            rows = original.execute('SELECT created_at,month,provider,model,kind,input_tokens,'
                                    'output_tokens,cost_usd,duration_ms FROM api_usage').fetchall()
        conn.executemany('INSERT INTO api_usage(user_id,created_at,month,provider,model,kind,'
                         'input_tokens,output_tokens,cost_usd,duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         [(user_id, *tuple(row)) for row in rows])
    return get_user(user_id)


_DUMMY_HASH = hash_password('not-a-real-user-password')


def authenticate(username: str, password: str) -> dict | None:
    with connection() as conn:
        row = conn.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username.strip(),)).fetchone()
    valid = verify_password(password, row['password_hash'] if row else _DUMMY_HASH)
    return dict(row) if row and valid and row['active'] else None


def create_invitation(admin_id: str, days: int = 7) -> dict:
    token, invite_id = secrets.token_urlsafe(32), secrets.token_hex(16)
    now = int(time.time())
    expires = now + days * 86400
    with connection() as conn:
        conn.execute('INSERT INTO invitations(id,token_hash,created_by,created_at,expires_at) VALUES (?,?,?,?,?)',
                     (invite_id, hashlib.sha256(token.encode()).hexdigest(), admin_id, now, expires))
    return {'id': invite_id, 'token': token, 'expires_at': expires}


def register(invitation: str, username: str, password: str) -> dict:
    username, digest = normalized_username(username), password_digest(password)
    user_id = secrets.token_hex(16)
    user = {'id': user_id, 'data_slot': user_id}
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        invite = conn.execute('SELECT * FROM invitations WHERE token_hash=?',
                              (hashlib.sha256(invitation.encode()).hexdigest(),)).fetchone()
        if not invite or invite['revoked'] or invite['used_by'] or invite['expires_at'] <= time.time():
            raise ValueError('邀请无效、已使用或已过期，请联系管理员')
        if conn.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone():
            raise ValueError('该用户名不可用')
        # A random server-owned directory, initialized before the identity becomes visible.
        path = data_path(user)
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=False)
        with path.open('xb'):
            pass
        path.chmod(0o600)
        with database.database_scope(path):
            database.init_db()
            database.backup_db()
        conn.execute('INSERT INTO users(id,username,password_hash,role,data_slot,created_at) '
                     "VALUES (?,?,?,'member',?,?)", (user_id, username, digest, user_id, int(time.time())))
        conn.execute('UPDATE invitations SET used_by=? WHERE id=?', (user_id, invite['id']))
    return get_user(user_id)


def list_users() -> list[dict]:
    with connection() as conn:
        return [dict(row) for row in conn.execute('SELECT * FROM users ORDER BY created_at,id')]


def change_password(user_id: str, current_password: str, new_password: str, username: str | None = None) -> dict:
    digest = password_digest(new_password)
    name = normalized_username(username) if username else None
    with connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        user = conn.execute('SELECT * FROM users WHERE id=? AND active=1', (user_id,)).fetchone()
        if not user or not verify_password(current_password, user['password_hash']):
            raise ValueError('当前密码不正确')
        if name and conn.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE AND id<>?', (name, user_id)).fetchone():
            raise ValueError('该用户名不可用')
        conn.execute('UPDATE users SET username=?,password_hash=?,session_version=session_version+1 WHERE id=?',
                     (name or user['username'], digest, user_id))
    return get_user(user_id)


def set_user_active(user_id: str, active: bool):
    with connection() as conn:
        row = conn.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            raise ValueError('账号不存在')
        if row['role'] == 'admin':
            raise ValueError('不能停用管理员账号')
        conn.execute('UPDATE users SET active=?,session_version=session_version+1 WHERE id=?', (int(active), user_id))


def backup_all():
    """Operator backups include the private catalog; user downloads never do."""
    from app.backups import snapshot
    from datetime import date
    if not store_path().exists():
        return
    backup_dir = store_path().parent / 'identity-backups'
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    destination = backup_dir / (store_path().stem + '-' + date.today().isoformat() + '.db')
    if not destination.exists():
        snapshot(store_path(), destination)
        destination.chmod(0o600)
    for old in sorted(backup_dir.glob(store_path().stem + '-20*.db'))[:-10]:
        old.unlink()
    for user in list_users():
        if user['data_slot'] == 'legacy':
            continue
        with database.database_scope(data_path(user), user['id']):
            database.backup_db()
