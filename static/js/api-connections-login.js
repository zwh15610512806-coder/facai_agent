(function () {
  'use strict';

  var form = document.getElementById('integrationLoginForm');
  var passwordInput = document.getElementById('integrationPassword');
  var submitButton = document.getElementById('integrationLoginSubmit');
  var errorBox = document.getElementById('integrationLoginError');
  var statusBox = document.getElementById('integrationLoginStatus');
  if (!form || !passwordInput || !submitButton) return;

  function showError(message) {
    errorBox.textContent = message || '登录失败，请稍后重试。';
    errorBox.hidden = false;
  }

  function clearMessages() {
    errorBox.hidden = true;
    errorBox.textContent = '';
    statusBox.textContent = '';
  }

  function apiMessage(data, fallback) {
    if (!data) return fallback;
    if (typeof data.detail === 'string') return data.detail;
    if (data.detail && typeof data.detail.message === 'string') return data.detail.message;
    return fallback;
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    clearMessages();
    var password = passwordInput.value;
    if (!password) {
      showError('请输入管理员密码。');
      passwordInput.focus();
      return;
    }

    submitButton.disabled = true;
    submitButton.setAttribute('aria-busy', 'true');
    statusBox.textContent = '正在验证身份…';
    var requestBody = JSON.stringify({password: password});
    password = '';
    passwordInput.value = '';

    try {
      var response = await fetch('/api/integrations/session', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: requestBody
      });
      requestBody = '';
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        if (response.status === 429 && Number(data.retry_after_seconds) > 0) {
          statusBox.textContent = '尝试次数过多，请在 ' + Number(data.retry_after_seconds) + ' 秒后重试。';
        }
        showError(apiMessage(data, '登录失败，请检查密码与安全配置。'));
        return;
      }
      if (!data.authenticated) {
        showError('登录响应无效，请重新尝试。');
        return;
      }
      var nextPath = form.dataset.next || '/app/api-connections';
      window.location.assign(nextPath);
    } catch (error) {
      requestBody = '';
      showError('无法连接接入服务，请确认本地服务正在运行。');
    } finally {
      submitButton.disabled = false;
      submitButton.removeAttribute('aria-busy');
      passwordInput.value = '';
    }
  });

  if (window.lucide) window.lucide.createIcons();
})();
