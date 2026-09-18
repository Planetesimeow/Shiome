"""One paid request at a time on the single-worker small-VPS deployment."""
from functools import wraps
from threading import BoundedSemaphore

_slot = BoundedSemaphore(1)


def single_model_call(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not _slot.acquire(blocking=False):
            return {'_api_error': '模型正在处理另一个请求，请稍后重试。', 'retryable': True}
        try:
            from app.database import get_conn, current_user_id
            from app.usage import budget_blocked
            if current_user_id():
                from app.identity import get_user
                user = get_user(current_user_id())
                if not user or not user['active']:
                    return {'_api_error': '账号已停用，请联系管理员。', 'retryable': False}
            with get_conn() as conn:
                blocked = budget_blocked(conn)
            if blocked:
                return blocked
            return function(*args, **kwargs)
        finally:
            _slot.release()
    return wrapped
