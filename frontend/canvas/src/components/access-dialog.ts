export interface AccessDialog {
  element: HTMLDialogElement;
  open(onUnlock: (token: string) => Promise<string | null>): void;
}

export function createAccessDialog(): AccessDialog {
  const element = document.createElement("dialog");
  element.className = "canvas-access-dialog";
  const form = document.createElement("form");
  const heading = document.createElement("h2");
  heading.textContent = "解锁付费生成";
  const notice = document.createElement("p");
  notice.textContent = "令牌仅用于本次解锁付费操作；在非本机 HTTP 环境请使用可信局域网与 HTTPS 反向代理。";
  const token = document.createElement("input");
  token.type = "password";
  token.autocomplete = "off";
  token.setAttribute("aria-label", "访问令牌");
  const feedback = document.createElement("p");
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "解锁并生成";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "取消";
  form.append(heading, notice, token, feedback, submit, cancel);
  element.append(form);
  cancel.addEventListener("click", () => element.close());
  let unlock: ((raw: string) => Promise<string | null>) | null = null;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (unlock === null || token.value === "") return;
    submit.disabled = true;
    void unlock(token.value).then((message) => {
      submit.disabled = false;
      if (message === null) element.close();
      else feedback.textContent = message;
    }).catch(() => {
      submit.disabled = false;
      feedback.textContent = "解锁失败，请重试";
    });
  });
  return {
    element,
    open: (onUnlock) => {
      unlock = onUnlock;
      feedback.textContent = "";
      token.value = "";
      element.showModal();
      token.focus();
    },
  };
}
