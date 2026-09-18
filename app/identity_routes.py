"""Account setup, invite-only registration and owner-only service administration."""
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app import identity
from app.auth import SESSION_COOKIE, make_session, verify_password

router = APIRouter()


def runtime():
    # One application config; tests and deployments may replace it at startup.
    from app import main
    return main


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Input):
    username: str = Field(default='', max_length=32)
    password: str = Field(max_length=128)


class Setup(Input):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)
    api_key: str | None = Field(default=None, max_length=512)


class Register(Input):
    invitation: str = Field(min_length=20, max_length=128)
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)


class PasswordChange(Input):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    username: str | None = Field(default=None, min_length=3, max_length=32)


class Invite(Input):
    days: int = Field(default=7, ge=1, le=30)


class KeyUpdate(Input):
    api_key: str = Field(min_length=10, max_length=512)


class UserState(Input):
    active: bool


def user_for(request: Request) -> dict:
    user = getattr(request.state, 'user', None)
    if not user or user.get('legacy'):
        raise HTTPException(409, '请先创建管理员账号')
    return user


def admin_for(request: Request) -> dict:
    user = user_for(request)
    if user['role'] != 'admin':
        raise HTTPException(403, '此操作仅限管理员')
    return user


def set_session(response: Response, request: Request, user: dict):
    auth = runtime().AUTH
    token = make_session(user['id'], auth.secret, auth.session_days, user['session_version'])
    response.set_cookie(SESSION_COOKIE, token, max_age=auth.session_days * 86400,
                        httponly=True, samesite='lax', secure=auth.production or request.url.scheme == 'https')


def verify_api_key(key: str):
    """Models lookup is free; never send a test generation or persist an unverified new key."""
    req = urllib.request.Request('https://api.anthropic.com/v1/models/claude-sonnet-5',
                                 headers={'x-api-key': key, 'anthropic-version': '2023-06-01'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            valid = json.load(response).get('id') == 'claude-sonnet-5'
    except (urllib.error.URLError, OSError, ValueError):
        raise HTTPException(400, '无法验证密钥或访问 Sonnet 5，请检查密钥后重试') from None
    if not valid:
        raise HTTPException(400, '此密钥无法访问 Sonnet 5')


def checked(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get('/setup')
@router.get('/register')
@router.get('/login')
def auth_page():
    return FileResponse(runtime().STATIC_DIR / 'login.html')


@router.get('/settings')
def settings_page(request: Request):
    user_for(request)
    return FileResponse(runtime().STATIC_DIR / 'settings.html')


@router.post('/api/auth/login')
def login(payload: Login, request: Request, response: Response):
    main = runtime()
    keys = [main._client_key(request), 'user:' + payload.username.strip().lower()]
    if not all(main.THROTTLE.check(key) for key in keys):
        raise HTTPException(429, '登录尝试过于频繁，请过一会儿再试')
    if identity.has_users():
        user = identity.authenticate(payload.username, payload.password)
        if user:
            for key in keys:
                main.THROTTLE.reset(key)
            set_session(response, request, user)
            return {'ok': True, 'setup_required': False, 'user': identity.public_user(user)}
    else:
        if not main.AUTH.configured:
            raise HTTPException(400, '尚未配置初始化口令')
        if main.AUTH.password_hash and verify_password(payload.password, main.AUTH.password_hash):
            for key in keys:
                main.THROTTLE.reset(key)
            token = make_session(main.AUTH.owner_id, main.AUTH.secret, main.AUTH.session_days)
            response.set_cookie(SESSION_COOKIE, token, max_age=main.AUTH.session_days * 86400,
                                httponly=True, samesite='lax', secure=main.AUTH.production or request.url.scheme == 'https')
            return {'ok': True, 'owner_id': main.AUTH.owner_id, 'setup_required': True}
    for key in keys:
        main.THROTTLE.record_failure(key)
    raise HTTPException(401, '用户名或密码不正确')


@router.post('/api/auth/logout')
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {'ok': True}


@router.get('/api/auth/status')
def auth_status(request: Request):
    main = runtime()
    user = main._authenticated_principal(request)
    configured = identity.has_users()
    result = {'configured': configured or main.AUTH.configured,
              'authenticated': user is not None, 'setup_required': not configured,
              'user': identity.public_user(user) if user and not user.get('legacy') else None}
    if user and user.get('legacy'):
        result['api_key_configured'] = identity.key_configured()
    return result


@router.post('/api/auth/setup')
def setup(payload: Setup, request: Request, response: Response):
    if not request.state.user.get('legacy') or identity.has_users():
        raise HTTPException(409, '管理员账号已创建')
    api_key = (payload.api_key or '').strip() or None
    if api_key:
        verify_api_key(api_key)
    elif not identity.key_configured():
        raise HTTPException(400, '请填写一次 Anthropic API 密钥')
    user = checked(identity.create_owner, payload.username, payload.password, runtime().AUTH.secret, api_key)
    set_session(response, request, user)
    return {'ok': True, 'user': identity.public_user(user)}


@router.post('/api/auth/register')
def register(payload: Register, request: Request, response: Response):
    main = runtime()
    key = 'register:' + main._client_key(request)
    if not main.THROTTLE.check(key):
        raise HTTPException(429, '注册尝试过于频繁，请稍后再试')
    if not identity.has_users():
        raise HTTPException(409, '管理员尚未完成初始化')
    try:
        user = identity.register(payload.invitation, payload.username, payload.password)
    except ValueError as exc:
        main.THROTTLE.record_failure(key)
        raise HTTPException(400, str(exc)) from None
    set_session(response, request, user)
    return {'ok': True, 'user': identity.public_user(user)}


@router.post('/api/auth/password')
def change_password(payload: PasswordChange, request: Request, response: Response):
    user = user_for(request)
    updated = checked(identity.change_password, user['id'], payload.current_password,
                      payload.new_password, payload.username)
    set_session(response, request, updated)
    return {'ok': True, 'user': identity.public_user(updated)}


@router.get('/api/admin/status')
def admin_status(request: Request):
    admin_for(request)
    from app.analysis.prompts import MODEL
    from app.vision import VISION_MODEL
    from app.usage import service_spend
    return {'api_key_configured': identity.key_configured(), 'analysis_model': MODEL,
            'vision_model': VISION_MODEL, 'usage': service_spend()}


@router.put('/api/admin/api-key')
def update_key(payload: KeyUpdate, request: Request):
    admin_for(request)
    key = payload.api_key.strip()
    verify_api_key(key)
    identity.save_key(key, runtime().AUTH.secret)
    return {'ok': True, 'api_key_configured': True}


@router.get('/api/admin/users')
def users(request: Request):
    admin_for(request)
    return [identity.public_user(user) for user in identity.list_users()]


@router.patch('/api/admin/users/{user_id}')
def update_user(user_id: str, payload: UserState, request: Request):
    admin_for(request)
    checked(identity.set_user_active, user_id, payload.active)
    return {'ok': True}


@router.post('/api/admin/invitations')
def invitation(payload: Invite, request: Request):
    user = admin_for(request)
    return identity.create_invitation(user['id'], payload.days)


@router.get('/api/admin/invitations')
def invitations(request: Request):
    admin_for(request)
    with identity.connection() as conn:
        return [dict(row) for row in conn.execute('SELECT id,created_at,expires_at,used_by,revoked '
                                                 'FROM invitations ORDER BY created_at DESC')]


@router.delete('/api/admin/invitations/{invite_id}')
def revoke_invitation(invite_id: str, request: Request):
    admin_for(request)
    with identity.connection() as conn:
        conn.execute('UPDATE invitations SET revoked=1 WHERE id=?', (invite_id,))
    return {'ok': True}
