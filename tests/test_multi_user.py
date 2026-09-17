"""Real API sessions, separate SQLite files and adversarial cross-user requests."""
import io
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import database, identity
from app.auth import AuthConfig, LoginThrottle, SESSION_COOKIE, hash_password

PASSWORD = 'a-long-test-password-123'
KEY = 'sk-ant-test-shared-key-never-send-to-network'


@pytest.fixture
def service(db_path, monkeypatch):
    from app import main, identity_routes
    monkeypatch.setattr(main, 'AUTH', AuthConfig({'SHIOME_PASSWORD_HASH': hash_password(PASSWORD),
                                                'SHIOME_SECRET_KEY': 'multi-user-test-secret-' * 3}))
    monkeypatch.setattr(main, 'THROTTLE', LoginThrottle())
    monkeypatch.setenv('SHIOME_MONTHLY_BUDGET_USD', '100')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(identity_routes, 'verify_api_key', lambda key: None)
    with ExitStack() as stack:
        def client():
            return stack.enter_context(TestClient(main.app, base_url='https://testserver'))
        owner = client()
        assert owner.post('/api/auth/login', json={'password': PASSWORD}).status_code == 200
        legacy_cookie = owner.cookies.get(SESSION_COOKIE)
        # Simulate the existing personal instance before its owner creates a username.
        for number in range(4):
            assert owner.post('/api/posts', json={'title': f'owner-private-{number}', 'publish_date': '2026-09-18'}).status_code == 200
        result = owner.post('/api/auth/setup', json={'username': 'owner', 'password': PASSWORD, 'api_key': KEY})
        assert result.status_code == 200, result.text
        owner_user = result.json()['user']
        invite = owner.post('/api/admin/invitations', json={}).json()
        member = client()
        result = member.post('/api/auth/register', json={'username': 'member', 'password': PASSWORD, 'invitation': invite['token']})
        assert result.status_code == 200, result.text
        member_user = result.json()['user']
        yield SimpleNamespace(owner=owner, member=member, owner_user=owner_user, member_user=member_user,
                              client=client, legacy_cookie=legacy_cookie, invite=invite, db_path=db_path)


def test_owner_setup_keeps_existing_data_and_invalidates_bootstrap_session(service):
    assert len(service.owner.get('/api/posts').json()) == 4
    assert service.member.get('/api/posts').json() == []
    assert identity.data_path(identity.get_user(service.owner_user['id'])) == service.db_path
    stale = service.client()
    stale.cookies.set(SESSION_COOKIE, service.legacy_cookie)
    assert stale.get('/api/posts').status_code == 401
    assert stale.post('/api/auth/login', json={'password': PASSWORD}).status_code == 401
    assert service.owner.post('/api/auth/setup', json={'username': 'other-owner', 'password': PASSWORD}).status_code == 409


def test_query_parameters_and_equal_ids_cannot_select_another_user(service):
    member_id = service.member.post('/api/posts', json={'title': 'member-only', 'publish_date': '2026-09-18'}).json()['id']
    assert member_id == 1  # IDs may overlap across users; their data must not.
    assert service.member.get('/api/posts/1').json()['title'] == 'member-only'
    assert service.owner.get('/api/posts/1').json()['title'] == 'owner-private-0'
    for suffix in (f'?owner_id={service.owner_user["id"]}', '?owner_id=local', '?user_id=../../shiome'):
        assert 'owner-private' not in service.member.get('/api/posts' + suffix).text
    assert database.current_db_path() == service.db_path
    assert database.current_user_id() is None


@pytest.mark.parametrize('method,path,payload', [
    ('GET', '/api/posts/4', None),
    ('DELETE', '/api/posts/4', None),
    ('PATCH', '/api/posts/4/content-profile', {'content_summary': 'overwrite attack'}),
    ('POST', '/api/posts/4/snapshots', {'checked_at': '2026-09-18T00:00:00Z', 'plays': 9999}),
    ('POST', '/api/analyze/posts/4/enhancement', None),
    ('POST', '/api/posts/merge', {'post_ids': [1, 4]}),
])
def test_foreign_post_cannot_be_read_edited_deleted_or_analyzed(service, monkeypatch, method, path, payload):
    from app.analysis import prompts
    monkeypatch.setattr(prompts, 'get_client', lambda: pytest.fail('must reject before a model call'))
    before = service.owner.get('/api/posts').json()
    response = service.member.request(method, path, json=payload)
    assert response.status_code in (400, 404, 422), response.text
    assert service.owner.get('/api/posts').json() == before


def test_all_data_surfaces_and_backups_are_private(service, tmp_path):
    owner = service.owner
    creative = owner.post('/api/creatives', json={'label': 'owner-secret-creative'}).json()['id']
    owner.post('/api/creator-notes', json={'body': 'owner-secret-note'})
    owner.post('/api/anomaly-periods', json={'start_date': '2026-09-01', 'end_date': '2026-09-30', 'reason': 'owner-secret-period'})
    owner.post('/api/posts/1/snapshots', json={'checked_at': '2026-09-18T00:00:00Z', 'plays': 999})
    with database.get_conn() as conn:
        conn.execute("INSERT INTO analysis_results(post_id,account_id,analysis_type,result_json) VALUES (1,1,'enhancement',?)",
                     (json.dumps({'diagnosis': ['owner-secret-analysis']}),))
    for path in ('/api/creatives', '/api/creator-notes', '/api/anomaly-periods', '/api/analyze/results',
                 '/api/account-metrics', '/api/posts/1/snapshots', '/api/posts/duplicate-candidates',
                 '/api/trend-data', '/api/baseline', '/api/report'):
        response = service.member.get(path)
        assert response.status_code in (200, 404), (path, response.text)
        assert 'owner-secret' not in response.text and 'owner-private' not in response.text
    assert service.member.get(f'/api/creatives/{creative}').status_code == 404
    assert service.member.patch(f'/api/creatives/{creative}', json={'label': 'attack'}).status_code == 404
    for person, expected in ((service.owner, 4), (service.member, 0)):
        backup = person.get('/api/backup')
        assert backup.status_code == 200
        assert KEY.encode() not in backup.content
        path = tmp_path / f'export-{expected}.db'
        path.write_bytes(backup.content)
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert conn.execute('SELECT COUNT(*) FROM posts').fetchone()[0] == expected
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert not tables & {'users', 'settings', 'invitations'}


@pytest.mark.parametrize('method,path,payload', [
    ('GET', '/api/admin/status', None), ('GET', '/api/admin/users', None),
    ('GET', '/api/admin/invitations', None), ('POST', '/api/admin/invitations', {}),
    ('PUT', '/api/admin/api-key', {'api_key': 'sk-ant-attacker-key'}),
    ('PATCH', '/api/admin/users/anything', {'active': False}),
    ('DELETE', '/api/admin/invitations/anything', None),
])
def test_member_cannot_administer_service(service, method, path, payload):
    assert service.member.request(method, path, json=payload).status_code == 403


def test_shared_key_is_encrypted_and_never_returned(service):
    assert identity.shared_api_key() == KEY
    assert KEY.encode() not in identity.store_path().read_bytes()
    for person in (service.owner, service.member):
        for path in ('/api/auth/status', '/api/usage', '/api/backup', '/settings'):
            response = person.get(path)
            assert KEY.encode() not in response.content
    assert KEY not in service.owner.get('/api/admin/status').text
    rotated = KEY + '-rotated'
    assert service.owner.put('/api/admin/api-key', json={'api_key': rotated}).status_code == 200
    assert identity.shared_api_key() == rotated
    assert rotated.encode() not in identity.store_path().read_bytes()


def test_invites_are_single_use_revocable_and_expire(service):
    visitor = service.client()
    def join(token, username='another'):
        return visitor.post('/api/auth/register', json={'username': username, 'password': PASSWORD, 'invitation': token})
    assert join(service.invite['token']).status_code == 400
    assert join('invalid-token-that-is-long-enough').status_code == 400
    invite = service.owner.post('/api/admin/invitations', json={}).json()
    service.owner.delete('/api/admin/invitations/' + invite['id'])
    assert join(invite['token']).status_code == 400
    invite = service.owner.post('/api/admin/invitations', json={}).json()
    with identity.connection() as conn:
        conn.execute('UPDATE invitations SET expires_at=0 WHERE id=?', (invite['id'],))
    assert join(invite['token']).status_code == 400
    assert KEY not in service.owner.get('/api/admin/invitations').text


def test_invitation_cannot_be_consumed_twice_concurrently(service):
    invite = service.owner.post('/api/admin/invitations', json={}).json()
    clients = [service.client(), service.client()]
    barrier = threading.Barrier(2)
    def join(index):
        barrier.wait(timeout=5)
        return clients[index].post('/api/auth/register', json={
            'username': f'racer{index}', 'password': PASSWORD, 'invitation': invite['token']}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(join, (0, 1))) == [200, 400]
    assert len(identity.list_users()) == 3


def test_registration_rejects_identity_injection_and_path_names(service):
    invite = service.owner.post('/api/admin/invitations', json={}).json()
    visitor = service.client()
    payload = {'username': 'new-user', 'password': PASSWORD, 'invitation': invite['token'], 'role': 'admin'}
    assert visitor.post('/api/auth/register', json=payload).status_code == 422
    payload.pop('role')
    payload['username'] = '../escape'
    assert visitor.post('/api/auth/register', json=payload).status_code == 400
    payload['username'] = 'new-user'
    assert visitor.post('/api/auth/register', json=payload).json()['user']['role'] == 'member'


def test_password_change_revokes_old_sessions_and_disabled_users_cannot_login(service):
    old_cookie = service.member.cookies.get(SESSION_COOKIE)
    new_password = PASSWORD + '-new'
    response = service.member.post('/api/auth/password', json={'current_password': PASSWORD, 'new_password': new_password})
    assert response.status_code == 200
    stale = service.client()
    stale.cookies.set(SESSION_COOKIE, old_cookie)
    assert stale.get('/api/posts').status_code == 401
    assert service.member.get('/api/posts').status_code == 200
    user_path = '/api/admin/users/' + service.member_user['id']
    assert service.owner.patch(user_path, json={'active': False}).status_code == 200
    assert service.member.get('/api/posts').status_code == 401
    assert service.member.post('/api/auth/login', json={'username': 'member', 'password': new_password}).status_code == 401
    assert service.owner.patch(user_path, json={'active': True}).status_code == 200
    assert service.member.get('/api/posts').status_code == 401
    assert service.member.post('/api/auth/login', json={'username': 'MEMBER', 'password': new_password}).status_code == 200
    assert service.owner.patch('/api/admin/users/' + service.owner_user['id'], json={'active': False}).status_code == 400


def test_cross_site_mutations_are_rejected(service):
    response = service.owner.post('/api/admin/invitations', json={}, headers={'origin': 'https://other.example'})
    assert response.status_code == 403
    assert service.member.post('/api/auth/logout', headers={'origin': 'https://other.example'}).status_code == 403


def test_stale_browser_cannot_save_under_a_different_login(service):
    before = service.member.get('/api/posts').json()
    response = service.member.post('/api/posts', json={'title': 'stale-owner-draft', 'publish_date': '2026-09-18'},
                                   headers={'X-Shiome-User': service.owner_user['id']})
    assert response.status_code == 409 and response.json()['account_changed']
    assert service.member.get('/api/posts').json() == before


def test_missing_data_file_fails_closed_for_requests_and_restart(service):
    from app.main import app
    path = identity.data_path(identity.get_user(service.member_user['id']))
    path.unlink()
    assert service.member.get('/api/posts').status_code == 503
    with pytest.raises(RuntimeError, match='database is missing'):
        with TestClient(app):
            pass
    assert not path.exists()
    service.db_path.unlink()
    with pytest.raises(RuntimeError, match='database is missing'):
        with TestClient(app):
            pass
    assert not service.db_path.exists()


def test_failed_key_validation_keeps_previous_key(service, monkeypatch):
    from app import identity_routes
    from fastapi import HTTPException
    def reject(_key):
        raise HTTPException(400, '无法验证密钥')
    monkeypatch.setattr(identity_routes, 'verify_api_key', reject)
    assert service.owner.put('/api/admin/api-key', json={'api_key': 'invalid-replacement'}).status_code == 400
    assert identity.shared_api_key() == KEY


def test_one_paid_call_at_a_time_and_budget_rechecked_inside_slot(service, monkeypatch):
    from app.model_calls import single_model_call
    from app.usage import record_usage
    entered, finish = threading.Event(), threading.Event()
    calls = []
    @single_model_call
    def paid_call():
        calls.append(database.current_user_id())
        entered.set()
        assert finish.wait(timeout=5)
        with database.get_conn() as conn:
            record_usage(conn, 'anthropic', 'claude-sonnet-5', 'test', 1000, 100)
        return {'ok': True}
    def request(user):
        with database.database_scope(identity.data_path(identity.get_user(user['id'])), user['id']):
            return paid_call()
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(request, service.owner_user)
        try:
            assert entered.wait(timeout=5)
            second = request(service.member_user)
            assert second['retryable'] and '_api_error' in second
        finally:
            finish.set()
        assert first.result(timeout=5) == {'ok': True}
    monkeypatch.setenv('SHIOME_MONTHLY_BUDGET_USD', '0.001')
    assert request(service.member_user)['_budget']['over_budget']
    assert len(calls) == 1


def test_operator_password_reset_invalidates_sessions(service, monkeypatch):
    from scripts import reset_user_password
    monkeypatch.setattr('sys.argv', ['reset_user_password', 'member'])
    monkeypatch.setattr(reset_user_password, 'getpass', lambda _: PASSWORD + '-reset')
    reset_user_password.main()
    assert service.member.get('/api/posts').status_code == 401
    assert service.member.post('/api/auth/login', json={'username': 'member', 'password': PASSWORD + '-reset'}).status_code == 200


def test_parallel_threaded_vision_preserves_user_scope_and_bills_shared_budget(service, monkeypatch):
    from app import main
    from app.usage import record_usage
    barrier = threading.Barrier(2)
    def extract(*args):
        user_id = database.current_user_id()
        barrier.wait(timeout=5)
        with database.get_conn() as conn:
            conn.execute('INSERT INTO creator_notes(body) VALUES (?)', (user_id,))
            record_usage(conn, 'anthropic', 'claude-sonnet-5', 'vision_extract', 1000, 100)
        return {'page_type': 'unknown', 'videos': [], 'marker': user_id}
    monkeypatch.setattr(main, 'extract_screenshot', extract)
    clients = [service.owner, service.member]
    def call(index):
        return clients[index].post('/api/vision/extract', files={'file': ('fixture.png', b'fake', 'image/png')}).json()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(call, (0, 1)))
    for index, user in enumerate((service.owner_user, service.member_user)):
        assert results[index]['marker'] == user['id']
        assert clients[index].get('/api/creator-notes').json()[0]['body'] == user['id']
        usage = clients[index].get('/api/usage').json()
        assert usage['calls'] == 1 and usage['shared_billing'] and usage['limit_usd'] is None
    assert service.owner.get('/api/admin/status').json()['usage']['calls'] == 2
    monkeypatch.setenv('SHIOME_MONTHLY_BUDGET_USD', '0.001')
    monkeypatch.setattr(main, 'extract_screenshot', lambda *_: pytest.fail('shared budget must block before extraction'))
    assert service.member.post('/api/vision/extract', files={'file': ('x.png', b'fake', 'image/png')}).json()['_budget']['over_budget']
    assert database.current_user_id() is None


def test_analysis_and_vision_use_sonnet_5_and_keep_results_private(service, monkeypatch):
    from app.analysis import prompts
    from app import vision
    captured = []
    def create(**kwargs):
        assert kwargs['model'] == 'claude-sonnet-5'
        assert kwargs['thinking'] == {'type': 'disabled'}
        assert kwargs['tool_choice']['name'] == 'emit_result'
        captured.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type='tool_use', name='emit_result', input={'diagnosis': ['member-result'], 'videos': [], 'page_type': 'unknown'})],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=20))
    monkeypatch.setattr(prompts, 'get_client', lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(prompts, 'MODEL', 'claude-sonnet-5')
    monkeypatch.setattr(vision, 'VISION_MODEL', 'claude-sonnet-5')
    member_id = service.member.post('/api/posts', json={'title': 'member-private-prompt', 'publish_date': '2026-09-18'}).json()['id']
    result = service.member.post(f'/api/analyze/posts/{member_id}/enhancement')
    assert result.status_code == 200, result.text
    assert 'member-private-prompt' in json.dumps(captured[0], ensure_ascii=False)
    assert 'owner-private' not in json.dumps(captured[0], ensure_ascii=False)
    assert service.owner.get('/api/analyze/results').json() == []
    assert len(service.member.get('/api/analyze/results').json()) == 1
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(image, format='PNG')
    assert service.member.post('/api/vision/extract', files={'file': ('fixture.png', image.getvalue(), 'image/png')}).status_code == 200
    assert len(captured) == 2
    assert service.owner.get('/api/usage').json()['calls'] == 0
    assert service.member.get('/api/usage').json()['calls'] == 2
