"""
鉴权。

从第一版 MEMO 起就写着「远程部署前必须补上」—— 现在补。设计取舍：

- **不装新依赖。** 口令哈希用 hashlib.scrypt，会话签名用 hmac，都是标准库。
  这个项目的依赖清单短是有意的，为了一个登录框引入一整套 auth 框架不划算。
- **两条通道。** 浏览器用签名 cookie（dashboard 是网页应用）；脚本和手机快捷指令用
  Authorization: Bearer（Phase 2 的手机采集要往接口直接 POST 图片）。
- **没配就锁死。** 没设口令也没设 token 时，只接受来自本机的请求，其他一律拒绝。
  这样本地开发照旧零配置，而「忘了配鉴权就丢到公网」这条路是走不通的 ——
  裸奔的默认值是这类工具最常见的事故。
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SESSION_COOKIE = "shiome_session"
DEFAULT_SESSION_DAYS = 30

# scrypt 参数：n=2^14 在普通机器上约 50-100ms，足够慢，登录又不会慢到烦人
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


# ---------- 口令 ----------

def hash_password(password: str, salt: bytes | None = None) -> str:
    """返回 'scrypt$<salt_hex>$<hash_hex>'，直接写进 SHIOME_PASSWORD_HASH。"""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """常数时间比较，避免按响应时间猜口令。格式不认识就当验证失败。"""
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                  n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(expected.hex(), digest_hex)


# ---------- 会话 ----------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_session(owner_id: str, secret: str, days: int = DEFAULT_SESSION_DAYS) -> str:
    payload = _b64(json.dumps({"sub": owner_id,
                               "exp": int(time.time()) + days * 86400}).encode())
    sig = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_session(token: str | None, secret: str) -> dict | None:
    """验签 + 查过期。任何一步不对都返回 None —— 不区分原因，也不抛异常。"""
    if not token or "." not in token:
        return None
    payload, _, sig = token.partition(".")
    expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data


# ---------- 配置 ----------

class AuthConfig:
    """从环境变量读一次。没配口令也没配 token 时 configured 为 False。"""

    def __init__(self, env: dict | None = None):
        e = env if env is not None else os.environ
        self.password_hash = (e.get("SHIOME_PASSWORD_HASH") or "").strip()
        self.api_token = (e.get("SHIOME_API_TOKEN") or "").strip()
        self.owner_id = (e.get("SHIOME_OWNER_ID") or "local").strip()
        try:
            self.session_days = int(e.get("SHIOME_SESSION_DAYS") or DEFAULT_SESSION_DAYS)
        except ValueError:
            self.session_days = DEFAULT_SESSION_DAYS
        # 会话密钥没配就从口令哈希派生：重启后会话依然有效，且不会静默生成一个
        # 每次重启都变的随机值（那会让人以为「登录老是掉」是 bug）。
        secret = (e.get("SHIOME_SECRET_KEY") or "").strip()
        self.secret_derived = not secret
        self.secret = secret or hashlib.sha256(
            (self.password_hash + self.api_token + "shiome-session").encode()).hexdigest()

    @property
    def configured(self) -> bool:
        return bool(self.password_hash or self.api_token)


def is_loopback(host: str | None) -> bool:
    return (host or "") in _LOOPBACK


# ---------- 登录限速 ----------

class LoginThrottle:
    """
    按来源 IP 限制登录尝试。内存里就够 —— 单机单进程，重启清零可以接受；
    这道闸挡的是在线暴力猜口令，不是持久化的风控。
    """

    def __init__(self, limit: int = 10, window_sec: int = 900):
        self.limit = limit
        self.window = window_sec
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        """True = 还可以试。"""
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        self._hits[key] = hits
        return len(hits) < self.limit

    def record_failure(self, key: str):
        self._hits.setdefault(key, []).append(time.time())

    def reset(self, key: str):
        self._hits.pop(key, None)
