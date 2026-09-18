const el = id => document.getElementById(id);
let currentUser;
async function api(path, method = 'GET', data) {
  const headers = { 'Content-Type': 'application/json' };
  if (currentUser) headers['X-Shiome-User'] = currentUser.id;
  const response = await fetch(path, { method, headers, ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
  if (response.status === 401) { location.href = '/login'; throw new Error('请重新登录'); }
  const body = await response.json().catch(() => ({}));
  if (body.account_changed) location.replace('/settings');
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '请检查输入后重试');
  return body;
}
async function action(button, work) {
  button.disabled = true;
  el('settings-message').textContent = '';
  try { await work(); }
  catch (err) { el('settings-message').textContent = err.message; }
  finally { button.disabled = false; }
}
function row(label, buttonLabel, actionHandler) {
  const item = document.createElement('div'); item.className = 'settings-row';
  const text = document.createElement('span'); text.textContent = label; item.append(text);
  if (buttonLabel) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'btn-ghost'; button.textContent = buttonLabel;
    button.addEventListener('click', () => action(button, actionHandler)); item.append(button);
  }
  return item;
}
async function loadAdmin() {
  const [status, users, invites] = await Promise.all([api('/api/admin/status'), api('/api/admin/users'), api('/api/admin/invitations')]);
  el('model-status').textContent = `${status.api_key_configured ? '密钥已配置' : '尚未配置密钥'} · 分析 ${status.analysis_model} · 识别 ${status.vision_model}`;
  const usage = status.usage;
  el('service-usage').textContent = `全站本月已使用 $${usage.spent_usd.toFixed(4)}${usage.limit_usd == null ? ' · 未设月度上限' : ` / $${usage.limit_usd.toFixed(2)} 月度预算`}`;
  el('users-list').replaceChildren(...users.map(user => row(`${user.username} · ${user.role === 'admin' ? '管理员' : user.active ? '使用中' : '已停用'}`,
    user.role === 'admin' ? null : user.active ? '停用' : '启用', async () => {
      await api('/api/admin/users/' + user.id, 'PATCH', { active: !user.active }); await loadAdmin();
      el('settings-message').textContent = '用户状态已更新';
    })));
  el('invitations-list').replaceChildren(...invites.map(invite => {
    const expired = invite.expires_at * 1000 <= Date.now();
    const state = invite.used_by ? '已使用' : invite.revoked ? '已撤销' : expired ? '已过期' : '待使用';
    return row(`${state} · ${new Date(invite.expires_at * 1000).toLocaleDateString()} 到期`, state === '待使用' ? '撤销' : null, async () => {
      await api('/api/admin/invitations/' + invite.id, 'DELETE'); await loadAdmin();
    });
  }));
}
el('credentials-form').addEventListener('submit', event => {
  event.preventDefault();
  action(event.submitter, async () => {
    if (el('new-password').value !== el('new-password-confirm').value) throw new Error('两次输入的新密码不一致');
    const result = await api('/api/auth/password', 'POST', { username: el('settings-username').value.trim(), current_password: el('current-password').value, new_password: el('new-password').value });
    currentUser = result.user;
    el('identity-label').textContent = currentUser.username;
    el('current-password').value = el('new-password').value = el('new-password-confirm').value = '';
    el('settings-message').textContent = '登录信息已更新，其他设备需要重新登录';
  });
});
el('key-form').addEventListener('submit', event => {
  event.preventDefault();
  action(event.submitter, async () => {
    await api('/api/admin/api-key', 'PUT', { api_key: el('shared-api-key').value.trim() });
    el('shared-api-key').value = ''; await loadAdmin();
    el('settings-message').textContent = '密钥已验证并保存';
  });
});
el('invite-form').addEventListener('submit', event => {
  event.preventDefault();
  action(event.submitter, async () => {
    const invite = await api('/api/admin/invitations', 'POST', { days: Number(el('invite-days').value) });
    el('invite-link').value = location.origin + '/register#invite=' + encodeURIComponent(invite.token);
    el('invite-result').hidden = false; await loadAdmin();
    el('settings-message').textContent = '邀请已创建，请把链接发给对方';
  });
});
el('copy-invite').addEventListener('click', event => action(event.currentTarget, async () => {
  try { await navigator.clipboard.writeText(el('invite-link').value); el('settings-message').textContent = '邀请链接已复制'; }
  catch (_) { el('invite-link').focus(); el('invite-link').select(); el('settings-message').textContent = '请复制已选中的邀请链接'; }
}));
el('settings-logout').addEventListener('click', event => action(event.currentTarget, async () => {
  await api('/api/auth/logout', 'POST'); location.href = '/login';
}));
async function init() {
  const status = await api('/api/auth/status');
  if (!status.authenticated) { location.replace('/login'); return; }
  if (status.setup_required) { location.replace('/setup'); return; }
  currentUser = status.user;
  el('identity-label').textContent = currentUser.username;
  el('settings-username').value = currentUser.username;
  if (currentUser.role === 'admin') { el('admin-settings').hidden = false; await loadAdmin(); }
}
init().catch(err => { el('settings-message').textContent = err.message; });
