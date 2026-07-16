(function () {
  var TOOL_LINKS = [
    {label: '数据导入', href: '/app/import', icon: 'upload'},
    {label: 'AI配置', href: '/app/ai-config', icon: 'settings'},
    {label: 'API接入', href: '/app/api-connections', icon: 'plug-zap'},
    {label: '产品视觉画布', href: '/app/canvas', icon: 'palette'}
  ];

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
  }

  function initToolNavigation() {
    if (!document.body || document.querySelector('.facai-tools-launcher')) return;

    var launcher = document.createElement('div');
    launcher.className = 'facai-tools-launcher';

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

    launcher.appendChild(menu);
    launcher.appendChild(toggle);
    document.body.appendChild(launcher);

    function setOpen(open, restoreFocus) {
      menu.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-label', open ? '关闭工具入口' : '打开工具入口');
      document.body.classList.toggle('facai-tools-open', open);
      if (!open && restoreFocus) toggle.focus();
    }

    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true', false);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        event.preventDefault();
        setOpen(false, true);
      }
    });
    document.addEventListener('click', function (event) {
      if (toggle.getAttribute('aria-expanded') === 'true' && !launcher.contains(event.target)) {
        setOpen(false, false);
      }
    });
    window.addEventListener('pagehide', function () {
      document.body.classList.remove('facai-tools-open');
    });
    if (window.lucide) window.lucide.createIcons();
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

  window.FacaiUI = {
    escHtml: escHtml,
    escAttr: escAttr,
    toast: toast,
    copyText: copyText,
    getApiErrorMessage: getApiErrorMessage,
    formatApiErrorMessage: formatApiErrorMessage,
    withBusyButton: withBusyButton,
    fetchWithTimeout: fetchWithTimeout,
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
