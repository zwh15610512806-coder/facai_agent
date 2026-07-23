(function () {
  var TOOL_LINKS = [
    {label: '数据导入', href: '/app/import', icon: 'upload'},
    {label: 'AI配置', href: '/app/ai-config', icon: 'settings'},
    {label: 'API接入', href: '/app/api-connections', icon: 'plug-zap'}
  ];
  var FACAI_CLIENT_ID_KEY = 'facai.client.id.v1';
  var FACAI_JOB_STATE_KEY = 'facai.jobs.observed.v1';
  var backgroundJobTimer = null;
  var backgroundJobs = [];

  function createUuid() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (ch) {
      var value = Math.random() * 16 | 0;
      return (ch === 'x' ? value : (value & 3 | 8)).toString(16);
    });
  }

  function getClientId() {
    var value = '';
    try { value = localStorage.getItem(FACAI_CLIENT_ID_KEY) || ''; } catch (error) {}
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)) {
      value = createUuid();
      try { localStorage.setItem(FACAI_CLIENT_ID_KEY, value); } catch (error) {}
    }
    return value;
  }

  function jobHeaders(extra) {
    var headers = new Headers(extra || {});
    headers.set('X-Facai-Client-Id', getClientId());
    return headers;
  }

  async function submitBackgroundJob(url, payload, options) {
    options = options || {};
    var headers = jobHeaders({'Content-Type': 'application/json'});
    headers.set('Idempotency-Key', options.idempotencyKey || createUuid());
    if (options.sourceRef) headers.set('X-Facai-Source-Ref', String(options.sourceRef));
    var response = await fetch(url, {method: 'POST', headers: headers, body: JSON.stringify(payload || {})});
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(formatApiErrorMessage(data.detail || data.message || data, '任务提交失败'));
    scheduleBackgroundJobPoll(100);
    return data.job || data;
  }

  async function fetchBackgroundJob(publicId) {
    var response = await fetch('/api/jobs/' + encodeURIComponent(publicId), {headers: jobHeaders({'Accept': 'application/json'})});
    if (!response.ok) throw new Error(await getApiErrorMessage(response, '任务读取失败'));
    return response.json();
  }

  async function changeBackgroundJob(publicId, action) {
    var response = await fetch('/api/jobs/' + encodeURIComponent(publicId) + '/' + action, {method: 'POST', headers: jobHeaders({'Accept': 'application/json'})});
    if (!response.ok) throw new Error(await getApiErrorMessage(response, '任务操作失败'));
    var job = await response.json();
    scheduleBackgroundJobPoll(100);
    return job;
  }

  async function waitForBackgroundJob(publicId, onUpdate) {
    while (true) {
      var job = await fetchBackgroundJob(publicId);
      if (typeof onUpdate === 'function') await onUpdate(job);
      if (['succeeded','failed','cancelled'].indexOf(job.status) >= 0) return job;
      await new Promise(function (resolve) { setTimeout(resolve, 1000); });
    }
  }

  function escHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch];
    });
  }

  function escAttr(value) {
    return escHtml(value).replace(/`/g, "&#96;");
  }

  function toast(message, type) {
    var el = document.createElement("div");
    el.className = "toast toast-" + (type === "success" || type === "ok" ? "ok" : "err");
    el.textContent = message || "";
    document.body.appendChild(el);
    setTimeout(function () {
      el.style.opacity = "0";
      el.style.transition = "opacity .3s";
      setTimeout(function () { el.remove(); }, 300);
    }, 2000);
  }

  function fallbackCopyText(text) {
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = String(text || "");
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      ta.style.top = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      ta.setSelectionRange(0, ta.value.length);
      try {
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        ok ? resolve() : reject(new Error("copy rejected"));
      } catch (error) {
        document.body.removeChild(ta);
        reject(error);
      }
    });
  }

  function copyText(text) {
    text = String(text || "");
    if (!text) return Promise.reject(new Error("empty"));
    return fallbackCopyText(text).catch(function () {
      if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
      throw new Error("copy rejected");
    });
  }

  async function getApiErrorMessage(response, fallback) {
    fallback = fallback || "操作失败";
    if (!response) return fallback;
    try {
      var data = await response.clone().json();
      return formatApiErrorMessage(data.detail || data.message || data, fallback);
    } catch (error) {
      try {
        var text = await response.clone().text();
        return text || fallback;
      } catch (innerError) {
        return fallback;
      }
    }
  }

  function formatApiErrorMessage(value, fallback) {
    fallback = fallback === undefined ? "操作失败" : fallback;
    if (value == null || value === "") return fallback;
    if (typeof value === "string") return value;
    if (Array.isArray(value)) {
      var parts = value.map(function (item) {
        return formatApiErrorMessage(item, "");
      }).filter(Boolean);
      return parts.join("；") || fallback;
    }
    if (typeof value === "object") {
      if (value.msg) return String(value.msg);
      if (value.message) return formatApiErrorMessage(value.message, fallback);
      if (value.detail) return formatApiErrorMessage(value.detail, fallback);
      if (value.loc || value.type) {
        var loc = Array.isArray(value.loc) ? value.loc.join(".") : (value.loc || "");
        var label = value.msg || value.type || fallback;
        return loc ? loc + "：" + label : String(label);
      }
      try {
        return JSON.stringify(value);
      } catch (error) {
        return fallback;
      }
    }
    return String(value);
  }

  async function withBusyButton(button, busyText, task) {
    if (!button) return task();
    var previousHtml = button.innerHTML;
    var previousDisabled = button.disabled;
    button.disabled = true;
    if (busyText) button.innerHTML = busyText;
    try {
      return await task();
    } finally {
      button.disabled = previousDisabled;
      button.innerHTML = previousHtml;
      if (window.lucide) window.lucide.createIcons();
    }
  }

  function renderPager(options) {
    var page = Math.max(1, Number(options.page || 1));
    var totalPages = Math.max(1, Number(options.totalPages || 1));
    var total = Math.max(0, Number(options.total || 0));
    var pageSize = Math.max(1, Number(options.pageSize || 20));
    var setPage = options.setPage || "setPage";
    var changePageSize = options.changePageSize || "changePageSize";
    var jumpToPage = options.jumpToPage || "jumpToPage";
    var sizes = options.sizes || [20, 40, 80];
    var html = "";
    html += '<button class="pager-btn" ' + (page <= 1 ? "disabled" : "") + ' onclick="' + setPage + "(" + (page - 1) + ')">‹</button>';
    html += '<span id="pageInfo" class="list-range">第 ' + page + " / " + totalPages + " 页，共 " + total + " 条</span>";
    html += '<select id="pageSize" class="input" style="width:auto;font-size:13px" onchange="' + changePageSize + '(this.value)">';
    sizes.forEach(function (size) {
      html += '<option value="' + size + '" ' + (pageSize === size ? "selected" : "") + ">" + size + " 条/页</option>";
    });
    html += "</select>";
    html += '<span class="pager-jump"><span>跳至</span><input id="pageJumpInput" type="number" min="1" max="' + totalPages + '" value="' + page + '" class="input pager-input" onkeydown="if(event.key===&quot;Enter&quot;)' + jumpToPage + '()"><span>页</span><button class="pager-btn" onclick="' + jumpToPage + '()">跳转</button></span>';
    html += '<button class="pager-btn" ' + (page >= totalPages ? "disabled" : "") + ' onclick="' + setPage + "(" + (page + 1) + ')">›</button>';
    return html;
  }

  function scrollActiveNavIntoView() {
    var active = document.querySelector('.nav-links .nav-link.on, .nav-links .nav-link[aria-current="page"]');
    if (!active || typeof active.scrollIntoView !== "function") return;
    try {
      active.scrollIntoView({block:'nearest',inline:'center'});
    } catch (error) {
      active.scrollIntoView();
    }
  }

  function fetchWithTimeout(input, init, timeoutMs) {
    init = Object.assign({}, init || {});
    timeoutMs = timeoutMs == null ? 30000 : Number(timeoutMs);
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return fetch(input, init);

    var controller = new AbortController();
    var upstreamSignal = init.signal;
    var abortFromUpstream = function () {
      controller.abort(upstreamSignal && upstreamSignal.reason);
    };
    if (upstreamSignal) {
      if (upstreamSignal.aborted) abortFromUpstream();
      else upstreamSignal.addEventListener("abort", abortFromUpstream, {once: true});
    }
    init.signal = controller.signal;

    var timer = setTimeout(function () {
      controller.abort(new DOMException("请求超时", "TimeoutError"));
    }, timeoutMs);
    return fetch(input, init).finally(function () {
      clearTimeout(timer);
      if (upstreamSignal) upstreamSignal.removeEventListener("abort", abortFromUpstream);
    });
  }

  async function fetchAllProducts(params) {
    var query = new URLSearchParams(params || {});
    var items = [];
    var page = 1;
    var totalPages = 1;
    do {
      query.set("page", String(page));
      query.set("per_page", "100");
      var response = await fetch("/api/products/page?" + query.toString());
      if (!response.ok) throw new Error("HTTP " + response.status);
      var payload = await response.json();
      if (!payload || !Array.isArray(payload.items)) {
        throw new Error("Invalid paged product response");
      }
      items = items.concat(payload.items);
      totalPages = Math.max(0, Number(payload.total_pages || 0));
      page += 1;
    } while (page <= totalPages);
    return items;
  }

  function isCurrentTool(item, pathname) {
    pathname = String(pathname || '/').split('?')[0].replace(/\/+$/, '') || '/';
    return pathname === item.href || pathname.indexOf(item.href + '/') === 0;
  }

  function currentToolLinks() {
    var pathname = window.location && window.location.pathname;
    return TOOL_LINKS.filter(function (item) {
      return !isCurrentTool(item, pathname);
    });
  }

  function createToolLink(item, className) {
    var link = document.createElement('a');
    link.className = className;
    link.href = item.href;

    var icon = document.createElement('i');
    icon.setAttribute('data-lucide', item.icon);
    icon.setAttribute('aria-hidden', 'true');
    link.appendChild(icon);

    var label = document.createElement('span');
    label.textContent = item.label;
    link.appendChild(label);
    return link;
  }

  function ensureMobileUtilityNavLinks() {
    var nav = document.querySelector('.nav-links');
    if (!nav || nav.querySelector('.nav-mobile-utility')) return;
    TOOL_LINKS.forEach(function (item) {
      if (!isCurrentTool(item, window.location && window.location.pathname)) {
        nav.appendChild(createToolLink(item, 'nav-link nav-mobile-utility'));
      }
    });
    if (!nav.querySelector('.nav-background-tasks')) {
      var taskLink = document.createElement('a');
      taskLink.className = 'nav-link nav-mobile-utility nav-background-tasks';
      taskLink.href = '#background-tasks';
      taskLink.innerHTML = '<i data-lucide="list-checks" aria-hidden="true"></i><span>后台任务</span>';
      taskLink.addEventListener('click', function (event) {
        event.preventDefault();
        openBackgroundTaskPanel(true);
      });
      nav.appendChild(taskLink);
    }
  }

  function jobTypeLabel(value) {
    var labels = {
      'ai.inspiration.chat': 'AI 工作',
      'ai.inspiration.document': '生成文档',
      'ai.scripts.generate': '生成脚本',
      'ai.scripts.rewrite': '脚本改写',
      'ai.products.rag': '产品资料问答',
      'ai.products.rag.scoped': '单产品问答',
      'ai.search.ai_search': 'AI 搜索',
      'ai.search.summary': '搜索结果汇总',
      'search_rebuild': '重建检索索引',
      'local_product_scan': '扫描产品资料',
      'local_script_scan': '扫描本地脚本',
      'workbook_import': 'Excel 脚本导入',
      'qianchuan_auto_match': '千川素材匹配',
      'maintenance.qianchuan.auto_match': '千川素材匹配'
      ,'maintenance.products.reindex': '重建产品索引'
      ,'maintenance.products.extract': '整理产品卖点'
      ,'maintenance.products.extract_all': '批量整理产品卖点'
      ,'integration.adapter.export': '集成数据导出'
    };
    return labels[value] || String(value || '后台任务').replace(/[._-]+/g, ' ');
  }

  function jobStatusLabel(value) {
    return ({pending:'排队中',running:'运行中',cancelling:'正在取消',succeeded:'已完成',failed:'失败',cancelled:'已取消'})[value] || value;
  }

  function readObservedJobs() {
    try { return JSON.parse(localStorage.getItem(FACAI_JOB_STATE_KEY) || '{}') || {}; } catch (error) { return {}; }
  }

  function writeObservedJobs(value) {
    try { localStorage.setItem(FACAI_JOB_STATE_KEY, JSON.stringify(value)); } catch (error) {}
  }

  function notifyJobTransitions(items) {
    var previous = readObservedJobs();
    var next = {};
    items.forEach(function (job) {
      var oldStatus = previous[job.public_id];
      next[job.public_id] = job.status;
      if ((oldStatus === 'pending' || oldStatus === 'running' || oldStatus === 'cancelling') && job.status === 'succeeded') {
        toast(jobTypeLabel(job.job_type) + '已完成', 'success');
        window.dispatchEvent(new CustomEvent('facai:job-completed', {detail: job}));
      } else if ((oldStatus === 'pending' || oldStatus === 'running' || oldStatus === 'cancelling') && job.status === 'failed') {
        toast(jobTypeLabel(job.job_type) + '执行失败', 'error');
      }
    });
    writeObservedJobs(next);
  }

  function renderBackgroundJobs() {
    var panel = document.getElementById('facaiTaskPanel');
    var list = document.getElementById('facaiTaskList');
    var toggle = document.getElementById('facaiTaskToggle');
    if (!panel || !list || !toggle) return;
    var activeCount = backgroundJobs.filter(function (job) { return ['pending','running','cancelling'].indexOf(job.status) >= 0; }).length;
    toggle.classList.toggle('has-active', activeCount > 0);
    toggle.setAttribute('aria-label', activeCount ? '后台任务，' + activeCount + ' 个运行中' : '后台任务');
    var badge = toggle.querySelector('.facai-task-badge');
    if (badge) { badge.textContent = String(activeCount); badge.hidden = activeCount < 1; }
    if (!backgroundJobs.length) {
      list.innerHTML = '<div class="facai-task-empty"><i data-lucide="check-circle-2"></i><span>暂无后台任务</span></div>';
    } else {
      list.innerHTML = backgroundJobs.map(function (job) {
        var active = ['pending','running','cancelling'].indexOf(job.status) >= 0;
        var adapter = String(job.job_type || '').indexOf('integration.adapter.') === 0;
        var progress = job.progress == null ? '' : '<span class="facai-task-progress"><span style="width:' + Math.max(0, Math.min(100, Number(job.progress))) + '%"></span></span>';
        var message = job.error_summary || job.message || '';
        var actions = '';
        if (active && !adapter) actions += '<button type="button" data-job-action="cancel" data-job-id="' + escAttr(job.public_id) + '">取消</button>';
        if (!adapter && (job.status === 'failed' || job.status === 'cancelled')) actions += '<button type="button" data-job-action="retry" data-job-id="' + escAttr(job.public_id) + '">重试</button>';
        if (job.status === 'succeeded') actions += '<button type="button" data-job-action="open" data-job-id="' + escAttr(job.public_id) + '">查看结果</button>';
        return '<article class="facai-task-item is-' + escAttr(job.status) + '"><div class="facai-task-item-head"><strong>' + escHtml(jobTypeLabel(job.job_type)) + '</strong><span>' + escHtml(jobStatusLabel(job.status)) + '</span></div>' + progress + '<p>' + escHtml(message) + '</p><div class="facai-task-actions">' + actions + '</div></article>';
      }).join('');
    }
    if (window.lucide) window.lucide.createIcons();
  }

  function scheduleBackgroundJobPoll(delay) {
    if (backgroundJobTimer) clearTimeout(backgroundJobTimer);
    backgroundJobTimer = setTimeout(pollBackgroundJobs, Math.max(50, Number(delay || 0)));
  }

  async function pollBackgroundJobs() {
    backgroundJobTimer = null;
    try {
      var response = await fetch('/api/jobs?limit=50', {headers: jobHeaders({'Accept': 'application/json'})});
      if (!response.ok) throw new Error('job poll ' + response.status);
      var payload = await response.json();
      backgroundJobs = Array.isArray(payload.items) ? payload.items : [];
      notifyJobTransitions(backgroundJobs);
      renderBackgroundJobs();
      var active = backgroundJobs.some(function (job) { return ['pending','running','cancelling'].indexOf(job.status) >= 0; });
      scheduleBackgroundJobPoll(active ? 2000 : 15000);
    } catch (error) {
      scheduleBackgroundJobPoll(10000);
    }
  }

  function openBackgroundTaskPanel(open) {
    var panel = document.getElementById('facaiTaskPanel');
    var toggle = document.getElementById('facaiTaskToggle');
    if (!panel || !toggle) return;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    document.body.classList.toggle('facai-tasks-open', open);
    if (open) scheduleBackgroundJobPoll(50);
  }

  function openBackgroundJob(job) {
    var target = String(job.origin_path || '/app');
    var separator = target.indexOf('?') >= 0 ? '&' : '?';
    target += separator + 'job=' + encodeURIComponent(job.public_id);
    if (job.source_ref) target += '&source_ref=' + encodeURIComponent(job.source_ref);
    if (window.location.pathname === String(job.origin_path || '/app')) {
      window.history.replaceState({}, '', target);
      window.dispatchEvent(new CustomEvent('facai:job-open', {detail: job}));
      openBackgroundTaskPanel(false);
      return;
    }
    window.location.href = target;
  }

  async function handleBackgroundTaskAction(event) {
    var button = event.target.closest('[data-job-action]');
    if (!button) return;
    var job = backgroundJobs.find(function (item) { return item.public_id === button.dataset.jobId; });
    if (!job) return;
    button.disabled = true;
    try {
      if (button.dataset.jobAction === 'open') {
        var detail = await fetchBackgroundJob(job.public_id);
        if (detail.result && detail.result.download_url) window.location.href = detail.result.download_url;
        else openBackgroundJob(detail);
      }
      else await changeBackgroundJob(job.public_id, button.dataset.jobAction);
    } catch (error) {
      toast(error.message || '任务操作失败', 'error');
    } finally {
      button.disabled = false;
    }
  }

  function initToolNavigation() {
    if (!document.body || document.querySelector('.facai-tools-launcher')) return;

    var launcher = document.createElement('div');
    launcher.className = 'facai-tools-launcher';

    var taskPanel = document.createElement('section');
    taskPanel.id = 'facaiTaskPanel';
    taskPanel.className = 'facai-task-panel';
    taskPanel.hidden = true;
    taskPanel.setAttribute('aria-label', '后台任务中心');
    taskPanel.innerHTML = '<div class="facai-task-panel-head"><div><strong>后台任务</strong><span>离开页面后仍会继续运行</span></div><button type="button" class="facai-task-close" aria-label="关闭后台任务">&times;</button></div><div id="facaiTaskList" class="facai-task-list"><div class="facai-task-empty">正在读取任务...</div></div>';

    var taskToggle = document.createElement('button');
    taskToggle.id = 'facaiTaskToggle';
    taskToggle.className = 'facai-tools-toggle facai-task-toggle';
    taskToggle.type = 'button';
    taskToggle.setAttribute('aria-expanded', 'false');
    taskToggle.setAttribute('aria-controls', 'facaiTaskPanel');
    taskToggle.setAttribute('aria-label', '后台任务');
    taskToggle.innerHTML = '<i data-lucide="list-checks" aria-hidden="true"></i><span>任务</span><b class="facai-task-badge" hidden>0</b>';

    var toggle = document.createElement('button');
    toggle.id = 'facaiToolsToggle';
    toggle.className = 'facai-tools-toggle';
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', 'facaiToolsMenu');
    toggle.setAttribute('aria-label', '打开工具入口');
    var toggleIcon = document.createElement('i');
    toggleIcon.setAttribute('data-lucide', 'wrench');
    toggleIcon.setAttribute('aria-hidden', 'true');
    toggle.appendChild(toggleIcon);
    var toggleLabel = document.createElement('span');
    toggleLabel.textContent = '工具';
    toggle.appendChild(toggleLabel);

    var menu = document.createElement('nav');
    menu.id = 'facaiToolsMenu';
    menu.className = 'facai-tools-menu';
    menu.setAttribute('aria-label', '工具入口');
    menu.hidden = true;
    currentToolLinks().forEach(function (item) {
      menu.appendChild(createToolLink(item, 'facai-tools-link'));
    });

    var controls = document.createElement('div');
    controls.className = 'facai-tools-controls';
    controls.appendChild(taskToggle);
    controls.appendChild(toggle);
    launcher.appendChild(taskPanel);
    launcher.appendChild(menu);
    launcher.appendChild(controls);
    document.body.appendChild(launcher);

    function setOpen(open, restoreFocus) {
      menu.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-label', open ? '关闭工具入口' : '打开工具入口');
      document.body.classList.toggle('facai-tools-open', open);
      if (!open && restoreFocus) toggle.focus();
    }

    toggle.addEventListener('click', function () {
      openBackgroundTaskPanel(false);
      setOpen(toggle.getAttribute('aria-expanded') !== 'true', false);
    });
    taskToggle.addEventListener('click', function () {
      setOpen(false, false);
      openBackgroundTaskPanel(taskToggle.getAttribute('aria-expanded') !== 'true');
    });
    taskPanel.querySelector('.facai-task-close').addEventListener('click', function () { openBackgroundTaskPanel(false); });
    taskPanel.addEventListener('click', handleBackgroundTaskAction);
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        event.preventDefault();
        setOpen(false, true);
      } else if (event.key === 'Escape' && taskToggle.getAttribute('aria-expanded') === 'true') {
        event.preventDefault();
        openBackgroundTaskPanel(false);
        taskToggle.focus();
      }
    });
    document.addEventListener('click', function (event) {
      if (toggle.getAttribute('aria-expanded') === 'true' && !launcher.contains(event.target)) {
        setOpen(false, false);
      }
      if (taskToggle.getAttribute('aria-expanded') === 'true' && !launcher.contains(event.target) && !event.target.closest('.nav-background-tasks')) {
        openBackgroundTaskPanel(false);
      }
    });
    window.addEventListener('pagehide', function () {
      document.body.classList.remove('facai-tools-open');
    });
    if (window.lucide) window.lucide.createIcons();
    scheduleBackgroundJobPoll(50);
  }

  if (document.readyState === "loading") {
    document.addEventListener('DOMContentLoaded', ensureMobileUtilityNavLinks);
    document.addEventListener('DOMContentLoaded', initToolNavigation);
    document.addEventListener('DOMContentLoaded', scrollActiveNavIntoView);
  } else {
    ensureMobileUtilityNavLinks();
    initToolNavigation();
    setTimeout(scrollActiveNavIntoView, 0);
  }
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) scheduleBackgroundJobPoll(50);
  });

  window.FacaiUI = {
    escHtml: escHtml,
    escAttr: escAttr,
    toast: toast,
    copyText: copyText,
    getApiErrorMessage: getApiErrorMessage,
    formatApiErrorMessage: formatApiErrorMessage,
    withBusyButton: withBusyButton,
    fetchWithTimeout: fetchWithTimeout,
    fetchAllProducts: fetchAllProducts,
    getClientId: getClientId,
    jobHeaders: jobHeaders,
    submitBackgroundJob: submitBackgroundJob,
    fetchBackgroundJob: fetchBackgroundJob,
    changeBackgroundJob: changeBackgroundJob,
    waitForBackgroundJob: waitForBackgroundJob,
    openBackgroundTaskPanel: openBackgroundTaskPanel,
    renderPager: renderPager,
    toolLinks: Object.freeze(TOOL_LINKS.map(function (item) {
      return Object.freeze({label: item.label, href: item.href, icon: item.icon});
    })),
    isCurrentTool: isCurrentTool,
    initToolNavigation: initToolNavigation,
    ensureMobileUtilityNavLinks: ensureMobileUtilityNavLinks,
    scrollActiveNavIntoView: scrollActiveNavIntoView
  };
})();
