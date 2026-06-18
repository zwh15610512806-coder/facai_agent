(function () {
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

  window.FacaiUI = {
    escHtml: escHtml,
    escAttr: escAttr,
    toast: toast,
    copyText: copyText,
    getApiErrorMessage: getApiErrorMessage,
    formatApiErrorMessage: formatApiErrorMessage,
    withBusyButton: withBusyButton,
    renderPager: renderPager
  };
})();
