(function () {
  'use strict';

  var center = document.getElementById('integrationCenter');
  if (!center) return;

  var providers = [];
  var connections = [];

  function notify(message, type) {
    if (window.FacaiUI && typeof window.FacaiUI.toast === 'function') {
      window.FacaiUI.toast(message, type || 'error');
    }
  }

  function setButtonBusy(button, busy) {
    if (!button) return;
    if (busy) {
      button.dataset.previousDisabled = button.disabled ? 'true' : 'false';
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
    } else {
      button.removeAttribute('aria-busy');
      button.disabled = button.dataset.previousDisabled === 'true';
      delete button.dataset.previousDisabled;
    }
  }

  async function apiErrorMessage(response, fallback) {
    if (window.FacaiUI && typeof window.FacaiUI.getApiErrorMessage === 'function') {
      return window.FacaiUI.getApiErrorMessage(response, fallback);
    }
    return fallback;
  }

  async function apiFetch(url, options, fallback) {
    options = options || {};
    var headers = options.headers || {};
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    options.headers = headers;
    options.credentials = 'same-origin';
    var response = await fetch(url, options);
    if (!response.ok) {
      var error = new Error(await apiErrorMessage(response, fallback || '请求失败，请稍后重试。'));
      error.status = response.status;
      throw error;
    }
    return response;
  }

  async function requestJson(url, options, fallback) {
    var response = await apiFetch(url, options, fallback);
    if (response.status === 204) return {};
    return response.json();
  }

  function formatValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (Array.isArray(value)) return value.length ? value.join('、') : '—';
    return String(value);
  }

  function formatTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return formatValue(value);
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    }).format(date);
  }

  function createRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    var hex = Array.from(bytes, function (value) { return value.toString(16).padStart(2, '0'); }).join('');
    return hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' + hex.slice(16, 20) + '-' + hex.slice(20);
  }

  function providerByName(name) {
    return providers.find(function (provider) { return provider.provider === name; }) || null;
  }

  function connectorReady(name) {
    var provider = providerByName(name);
    return Boolean(provider && provider.live_verified);
  }

  function renderProviderStatus(provider) {
    var row = document.querySelector('[data-provider="' + provider.provider + '"]');
    if (!row) return;
    var config = provider.app_config || {};
    var appId = row.querySelector('[name="app_id"]');
    var ready = Boolean(provider.live_verified);
    row.dataset.connectorReady = ready ? 'true' : 'false';
    row.querySelector('.provider-config-state').textContent = provider.configured ? (ready ? '应用已配置' : '已配置，待连接器') : '待配置';
    if (document.activeElement !== appId) appId.value = config.app_id || '';
    row.querySelector('.provider-secret-mask').textContent = config.secret_configured ? (config.secret_mask || '已安全保存') : '未配置';
    row.querySelector('.provider-capability strong').textContent = ready ? '连接器已验收' : '待资料验收';
    var authorize = row.querySelector('[data-provider-authorize]');
    authorize.disabled = !(ready && provider.configured);
    authorize.title = ready ? (provider.configured ? '开始官方授权' : '请先保存 App ID 与 Secret') : '连接器未配置';
  }

  function connectionId(connection) {
    return String(connection.id || connection.connection_id || '');
  }

  function connectionName(connection) {
    return connection.display_name || connection.account_name || connection.external_account_id || connectionId(connection);
  }

  function connectionAuthorizationId(connection) {
    return connection.authorization_id || (connection.authorization && connection.authorization.id) || '';
  }

  function connectionScopes(connection) {
    if (Array.isArray(connection.scopes)) return connection.scopes;
    if (connection.authorization && Array.isArray(connection.authorization.scopes)) return connection.authorization.scopes;
    return [];
  }

  function connectionResources(connection) {
    var capabilities = connection.capabilities;
    var values = Array.isArray(capabilities) ? capabilities : (capabilities && capabilities.verified_resources) || [];
    return values.filter(function (resource) { return resource && resource !== 'order_items'; });
  }

  function createMeta(label, value) {
    var item = document.createElement('div');
    item.className = 'integration-connection-meta';
    var key = document.createElement('span');
    key.textContent = label;
    var content = document.createElement('strong');
    content.textContent = formatValue(value);
    item.append(key, content);
    return item;
  }

  function actionButton(label, action, context) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-soft btn-sm';
    button.dataset.connectionAction = action;
    button.textContent = label;
    if (context) button.setAttribute('aria-label', label + ' ' + context);
    return button;
  }

  function renderConnections() {
    var list = document.getElementById('connectionList');
    list.replaceChildren();
    if (!connections.length) {
      var empty = document.createElement('div');
      empty.className = 'integration-connection-empty';
      empty.textContent = '暂无已授权连接。连接器未配置时可先保存平台应用信息。';
      list.appendChild(empty);
      return;
    }
    connections.forEach(function (connection) {
      var card = document.createElement('article');
      card.className = 'integration-connection-card';
      card.dataset.connectionId = connectionId(connection);
      card.dataset.displayName = connectionName(connection);
      card.dataset.authorizationId = connectionAuthorizationId(connection);

      var identity = document.createElement('div');
      var title = document.createElement('h4');
      title.textContent = connectionName(connection);
      var detail = document.createElement('p');
      detail.textContent = formatValue(connection.provider) + ' · ' + formatValue(connection.external_account_id);
      identity.append(title, detail);
      card.appendChild(identity);
      card.appendChild(createMeta('连接状态', connection.status));
      card.appendChild(createMeta('授权 scope', connectionScopes(connection)));
      var authorization = connection.authorization || {};
      card.appendChild(createMeta('凭据 / 到期', formatValue(authorization.access_token_mask || connection.credential_mask) + ' · ' + formatTime(authorization.access_expires_at || connection.token_expires_at)));
      card.appendChild(createMeta('能力 / 最近同步', formatValue(connectionResources(connection)) + ' · ' + formatTime(connection.last_successful_sync_at || connection.last_sync_at)));

      var actions = document.createElement('div');
      actions.className = 'integration-connection-actions';
      var name = connectionName(connection);
      var sync = actionButton('立即同步', 'sync', name);
      var reauthorize = actionButton('重新授权', 'reauthorize', name);
      var disable = actionButton('停用', 'disable', name);
      var revoke = actionButton('清除本地凭据', 'revoke', name);
      var purge = actionButton('永久清除', 'purge', name);
      purge.classList.add('integration-danger-link');
      var ready = connectorReady(connection.provider);
      sync.disabled = !ready || !connectionResources(connection).length || ['active', 'permission_limited'].indexOf(connection.status) < 0;
      reauthorize.disabled = !ready;
      sync.title = ready ? '' : '连接器未配置';
      reauthorize.title = ready ? '' : '连接器未配置';
      revoke.disabled = !connectionAuthorizationId(connection);
      revoke.title = '仅清除本地凭据；平台侧仍需前往官方后台撤销。';
      actions.append(sync, reauthorize, disable, revoke, purge);
      card.appendChild(actions);
      list.appendChild(card);
    });
  }

  function createCell(value) {
    var cell = document.createElement('td');
    if (value instanceof Node) cell.appendChild(value);
    else cell.textContent = formatValue(value);
    return cell;
  }

  function renderFailedRuns(data) {
    var panel = document.getElementById('failedSyncRuns');
    var state = panel.querySelector('[data-failed-state]');
    var wrap = panel.querySelector('[data-failed-wrap]');
    var body = panel.querySelector('[data-failed-body]');
    var items = (data.items || []).filter(function (item) { return ['failed', 'partial_success'].indexOf(item.status) >= 0; });
    body.replaceChildren();
    if (!items.length) {
      state.hidden = false;
      state.dataset.state = 'empty';
      state.textContent = '当前没有需要重试的失败任务。';
      wrap.hidden = true;
      return;
    }
    items.forEach(function (item) {
      var id = String(item.id || item.run_id || item.public_id || '');
      var retry = actionButton('重试', 'retry-run', '同步任务 ' + id);
      retry.dataset.runId = id;
      var row = document.createElement('tr');
      [item.public_id || item.run_id || item.id, item.connection_name || item.connection_id, item.resource_type, item.status, item.failure_summary, formatTime(item.window_start) + ' – ' + formatTime(item.window_end), retry].forEach(function (value) {
        row.appendChild(createCell(value));
      });
      body.appendChild(row);
    });
    state.hidden = true;
    wrap.hidden = false;
  }

  function disableCredentialWrites() {
    document.querySelectorAll('[data-provider-config] input,[data-provider-config] button,.integration-connection-actions button').forEach(function (control) {
      control.disabled = true;
      control.title = '安全配置未完成';
    });
  }

  async function refreshProviders() {
    var data = await requestJson('/api/integrations/providers', {}, '平台状态暂时无法读取。');
    providers = data.providers || [];
    providers.forEach(renderProviderStatus);
  }

  async function refreshConnections() {
    var data = await requestJson('/api/integrations/connections', {}, '连接列表暂时无法读取。');
    connections = data.items || data.connections || [];
    renderConnections();
  }

  async function refreshFailedRuns() {
    var panel = document.getElementById('failedSyncRuns');
    panel.setAttribute('aria-busy', 'true');
    try {
      var data = await requestJson('/api/integrations/sync-runs?per_page=50', {}, '失败任务暂时无法读取。');
      renderFailedRuns(data);
    } finally {
      panel.setAttribute('aria-busy', 'false');
    }
  }

  async function saveProviderConfig(form) {
    var button = form.querySelector('[data-provider-save]');
    var appId = form.elements.app_id.value.trim();
    var secret = form.elements.app_secret.value;
    if (!appId) {
      notify('请填写 App ID。');
      form.elements.app_id.focus();
      return;
    }
    var payload = {app_id: appId, clear_secret: false};
    if (secret) payload.app_secret = secret;
    form.elements.app_secret.value = '';
    secret = '';
    setButtonBusy(button, true);
    try {
      await requestJson('/api/integrations/providers/' + encodeURIComponent(form.dataset.providerConfig) + '/app-config', {method: 'PUT', body: JSON.stringify(payload)}, '应用配置保存失败。');
      notify('应用配置已安全保存。', 'success');
      await refreshProviders();
    } catch (error) {
      if (!error.isAuthRedirect) notify(error.message);
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function authorizeProvider(row, button) {
    if (row.dataset.connectorReady !== 'true') return;
    setButtonBusy(button, true);
    try {
      var data = await requestJson('/api/integrations/providers/' + encodeURIComponent(row.dataset.provider) + '/authorize', {method: 'POST', body: JSON.stringify({return_path: '/app/api-connections'})}, '暂时无法发起授权。');
      if (!data.authorization_url) throw new Error('授权地址无效。');
      window.location.assign(data.authorization_url);
    } catch (error) {
      if (!error.isAuthRedirect) notify(error.message);
      setButtonBusy(button, false);
    }
  }

  function shanghaiDate(value) {
    var parts = new Intl.DateTimeFormat('en', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(value);
    var selected = {};
    parts.forEach(function (part) { if (part.type !== 'literal') selected[part.type] = part.value; });
    return selected.year + '-' + selected.month + '-' + selected.day;
  }

  function defaultSyncBody(connection) {
    var end = new Date();
    var start = new Date(end.getTime() - 6 * 24 * 60 * 60 * 1000);
    var resources = connectionResources(connection);
    return {resources: resources.length ? [resources[0]] : ['orders'], date_from: shanghaiDate(start), date_to: shanghaiDate(end), request_id: createRequestId()};
  }

  async function runConnectionAction(card, button) {
    var action = button.dataset.connectionAction;
    if (action === 'purge') {
      openPurgeDialog(card);
      return;
    }
    var id = card.dataset.connectionId;
    var method = 'POST';
    var path = '/api/integrations/connections/' + encodeURIComponent(id) + '/' + action;
    var body;
    var connection = connections.find(function (item) { return connectionId(item) === id; }) || {};
    if (action === 'sync') body = defaultSyncBody(connection);
    if (action === 'reauthorize') body = {return_path: '/app/api-connections'};
    if (action === 'disable') { method = 'DELETE'; path = '/api/integrations/connections/' + encodeURIComponent(id); }
    if (action === 'revoke') { method = 'DELETE'; path = '/api/integrations/authorizations/' + encodeURIComponent(card.dataset.authorizationId); }
    setButtonBusy(button, true);
    try {
      var data = await requestJson(path, {method: method, body: body ? JSON.stringify(body) : undefined}, '连接操作失败。');
      if (data.authorization_url) window.location.assign(data.authorization_url);
      else {
        notify('操作已提交。', 'success');
        await Promise.all([refreshConnections(), refreshFailedRuns()]);
      }
    } catch (error) {
      if (!error.isAuthRedirect) notify(error.message);
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function retryRun(button) {
    setButtonBusy(button, true);
    try {
      await requestJson('/api/integrations/sync-runs/' + encodeURIComponent(button.dataset.runId) + '/retry', {method: 'POST', body: JSON.stringify({request_id: createRequestId()})}, '同步任务重试失败。');
      notify('重试任务已提交。', 'success');
      await refreshFailedRuns();
    } catch (error) {
      if (!error.isAuthRedirect) notify(error.message);
    } finally {
      setButtonBusy(button, false);
    }
  }

  var purgeDialog = document.getElementById('purgeConnectionDialog');
  var purgeForm = purgeDialog.querySelector('[data-purge-form]');

  function updatePurgeSubmit() {
    var expected = purgeDialog.querySelector('[data-purge-display-name]').textContent;
    purgeDialog.querySelector('[data-purge-submit]').disabled = purgeForm.elements.confirmation.value !== expected;
  }

  function openPurgeDialog(card) {
    purgeForm.reset();
    purgeForm.elements.connection_id.value = card.dataset.connectionId;
    purgeDialog.querySelector('[data-purge-display-name]').textContent = card.dataset.displayName;
    purgeDialog.querySelector('[data-purge-status]').textContent = '';
    updatePurgeSubmit();
    purgeDialog.showModal();
  }

  async function submitPurge(event) {
    event.preventDefault();
    var submit = purgeDialog.querySelector('[data-purge-submit]');
    var confirmation = purgeForm.elements.confirmation.value;
    setButtonBusy(submit, true);
    try {
      await requestJson('/api/integrations/connections/' + encodeURIComponent(purgeForm.elements.connection_id.value) + '/purge', {method: 'POST', body: JSON.stringify({confirmation: confirmation})}, '永久清除任务提交失败。');
      confirmation = '';
      purgeDialog.close();
      notify('永久清除任务已进入安全队列。', 'success');
      await refreshConnections();
    } catch (error) {
      confirmation = '';
      if (!error.isAuthRedirect) purgeDialog.querySelector('[data-purge-status]').textContent = error.message;
    } finally {
      setButtonBusy(submit, false);
      updatePurgeSubmit();
    }
  }

  async function refreshAll() {
    var button = document.getElementById('integrationRefresh');
    var panel = document.getElementById('connectionManagement');
    var status = document.getElementById('connectionPanelStatus');
    setButtonBusy(button, true);
    panel.setAttribute('aria-busy', 'true');
    status.textContent = '正在读取平台、连接与失败任务…';
    try {
      var results = await Promise.allSettled([refreshProviders(), refreshConnections(), refreshFailedRuns()]);
      if (center.dataset.credentialReady !== 'true') disableCredentialWrites();
      var failed = results.find(function (result) { return result.status === 'rejected'; });
      if (failed) throw failed.reason;
      status.textContent = center.dataset.credentialReady === 'true' ? '平台与连接状态已更新。' : '历史数据可读取；安全配置未完成，写入操作保持关闭。';
    } catch (error) {
      if (!error.isAuthRedirect) {
        status.textContent = error.message || '平台状态暂时无法刷新。';
        notify(status.textContent);
      }
    } finally {
      panel.setAttribute('aria-busy', 'false');
      setButtonBusy(button, false);
      if (window.lucide) window.lucide.createIcons();
    }
  }

  document.getElementById('integrationRefresh').addEventListener('click', refreshAll);
  document.getElementById('providerConnectionList').addEventListener('submit', function (event) {
    var form = event.target.closest('[data-provider-config]');
    if (!form) return;
    event.preventDefault();
    saveProviderConfig(form);
  });
  document.getElementById('providerConnectionList').addEventListener('click', function (event) {
    var button = event.target.closest('[data-provider-authorize]');
    if (button) authorizeProvider(button.closest('[data-provider]'), button);
  });
  document.getElementById('connectionList').addEventListener('click', function (event) {
    var button = event.target.closest('[data-connection-action]');
    if (button) runConnectionAction(button.closest('[data-connection-id]'), button);
  });
  document.getElementById('failedSyncRuns').addEventListener('click', function (event) {
    var button = event.target.closest('[data-connection-action="retry-run"]');
    if (button) retryRun(button);
  });
  purgeForm.addEventListener('input', updatePurgeSubmit);
  purgeForm.addEventListener('submit', submitPurge);
  purgeDialog.querySelectorAll('[data-dialog-close]').forEach(function (button) {
    button.addEventListener('click', function () { purgeDialog.close(); });
  });

  refreshAll();
  if (window.lucide) window.lucide.createIcons();
})();
