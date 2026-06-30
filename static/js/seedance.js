(function () {
  var ui = window.FacaiUI || {};
  var escHtml = ui.escHtml || function (value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch];
    });
  };
  var toast = ui.toast || function (message) { window.alert(message); };
  var copyText = ui.copyText || function (text) { return navigator.clipboard.writeText(text); };
  var getApiErrorMessage = ui.getApiErrorMessage || async function (response, defaultMessage) {
    try {
      var data = await response.json();
      return data.detail || data.message || defaultMessage;
    } catch (error) {
      return defaultMessage;
    }
  };

  var state = {
    items: [],
    promptText: "",
    lastRequest: null,
    generating: false
  };

  function el(id) { return document.getElementById(id); }

  function scriptText() {
    return (el("seedanceScriptInput").value || "").trim();
  }

  function updateCharCount() {
    el("seedanceCharCount").textContent = (el("seedanceScriptInput").value || "").length + " 字";
  }

  function setStatus(text) {
    el("seedanceStatus").textContent = text || "";
  }

  function setGenerating(isGenerating) {
    state.generating = isGenerating;
    el("btnGenerateSeedancePrompts").disabled = isGenerating;
    el("btnRegenerateSeedance").disabled = isGenerating || !state.lastRequest;
    el("btnCopySeedanceAll").disabled = isGenerating || !state.promptText;
    if (isGenerating) {
      el("btnGenerateSeedancePrompts").innerHTML = '<span class="spin" style="width:16px;height:16px;border-width:2px"></span>生成中';
      setStatus("生成中...");
    } else {
      el("btnGenerateSeedancePrompts").innerHTML = '<i data-lucide="sparkles" style="width:16px;height:16px"></i>生成提示词';
    }
    if (window.lucide) window.lucide.createIcons();
  }

  function buildRequest() {
    if (!scriptText()) {
      toast("请先粘贴或上传脚本", "error");
      return null;
    }
    return {
      script_content: scriptText(),
      requirements: (el("seedanceRequirements").value || "").trim() || null
    };
  }

  async function uploadScriptFile(file) {
    if (!file) return;
    var button = el("btnUploadSeedanceScript");
    button.disabled = true;
    setStatus("解析文件...");
    try {
      var form = new FormData();
      form.append("file", file);
      var response = await fetch("/api/scripts/seedance-prompts/upload", {method: "POST", body: form});
      if (!response.ok) throw new Error(await getApiErrorMessage(response, "上传失败"));
      var data = await response.json();
      el("seedanceScriptInput").value = data.text || "";
      el("seedanceFileName").textContent = data.filename + " · " + data.char_count + " 字";
      updateCharCount();
      resetResult("文件已解析，可生成提示词。");
      toast("脚本已读取", "success");
    } catch (error) {
      toast(error.message || "上传失败", "error");
      setStatus("上传失败");
    } finally {
      button.disabled = false;
    }
  }

  async function generatePrompts(request) {
    setGenerating(true);
    renderLoading();
    try {
      var response = await fetch("/api/scripts/seedance-prompts", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(request)
      });
      if (!response.ok) throw new Error(await getApiErrorMessage(response, "生成失败"));
      var data = await response.json();
      state.items = data.items || [];
      state.promptText = data.prompt_text || "";
      state.lastRequest = request;
      renderPrompts(data);
      setStatus("已生成 " + state.items.length + " 条");
      toast("DeepSeek V4 Pro 提示词已生成", "success");
    } catch (error) {
      resetResult(error.message || "生成失败");
      setStatus("生成失败");
      toast(error.message || "生成失败", "error");
    } finally {
      setGenerating(false);
    }
  }

  function renderLoading() {
    el("seedancePromptList").innerHTML = '<div class="seedance-loading"><div class="spin" style="width:32px;height:32px;border-width:3px;margin-bottom:12px"></div><div>正在生成...</div></div>';
  }

  function resetResult(message) {
    state.items = [];
    state.promptText = "";
    el("seedanceSource").style.display = "none";
    el("btnCopySeedanceAll").disabled = true;
    el("btnRegenerateSeedance").disabled = !state.lastRequest;
    el("seedancePromptList").innerHTML = '<div class="seedance-empty">' + escHtml(message || "生成后在这里查看分镜提示词。") + "</div>";
  }

  function renderPrompts(data) {
    var source = el("seedanceSource");
    source.style.display = "";
    source.textContent = "DeepSeek V4 Pro";
    el("btnCopySeedanceAll").disabled = !state.promptText;
    el("btnRegenerateSeedance").disabled = false;
    if (!state.items.length) {
      resetResult("未生成可用提示词。");
      return;
    }
    el("seedancePromptList").innerHTML = state.items.map(function (item, index) {
      return '<article class="seedance-card">' +
        '<div class="seedance-card-hd"><span class="seedance-scene">画面' + item.scene_number + ' · ' + escHtml(item.label || "Seedance 画面") + '</span>' +
        '<button class="btn btn-soft btn-sm seedance-copy-one" type="button" data-index="' + index + '">复制</button></div>' +
        '<div class="seedance-prompt">' + escHtml(item.prompt || "") + '</div>' +
        '</article>';
    }).join("");
  }

  function copyAllPrompts() {
    if (!state.promptText) {
      toast("暂无可复制内容", "error");
      return;
    }
    copyText(state.promptText).then(function () {
      toast("已成功复制到剪贴板", "success");
    }).catch(function () {
      toast("复制失败，请手动选中文案复制", "error");
    });
  }

  function copyOnePrompt(index) {
    var item = state.items[index];
    if (!item || !item.prompt) return;
    copyText(item.prompt).then(function () {
      toast("已成功复制到剪贴板", "success");
    }).catch(function () {
      toast("复制失败，请手动选中文案复制", "error");
    });
  }

  function bindEvents() {
    el("seedanceScriptInput").addEventListener("input", function () {
      updateCharCount();
      state.lastRequest = null;
      resetResult("脚本已更新，可生成新的提示词。");
      setStatus("待生成");
    });
    el("seedanceRequirements").addEventListener("input", function () {
      if (state.lastRequest) {
        state.lastRequest = null;
        resetResult("需求已更新，可生成新的提示词。");
        setStatus("待生成");
      }
    });
    el("btnUploadSeedanceScript").addEventListener("click", function () {
      el("seedanceFileInput").click();
    });
    el("seedanceFileInput").addEventListener("change", function () {
      uploadScriptFile(this.files && this.files[0]);
      this.value = "";
    });
    el("btnClearSeedanceScript").addEventListener("click", function () {
      el("seedanceScriptInput").value = "";
      el("seedanceFileName").textContent = "未选择文件";
      updateCharCount();
      state.lastRequest = null;
      resetResult("生成后在这里查看分镜提示词。");
      setStatus("待生成");
    });
    el("btnGenerateSeedancePrompts").addEventListener("click", function () {
      var request = buildRequest();
      if (request) generatePrompts(request);
    });
    el("btnRegenerateSeedance").addEventListener("click", function () {
      if (state.lastRequest) generatePrompts(state.lastRequest);
    });
    el("btnCopySeedanceAll").addEventListener("click", copyAllPrompts);
    el("seedancePromptList").addEventListener("click", function (event) {
      var button = event.target.closest(".seedance-copy-one");
      if (!button) return;
      copyOnePrompt(Number(button.dataset.index));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindEvents();
    updateCharCount();
  });
})();
