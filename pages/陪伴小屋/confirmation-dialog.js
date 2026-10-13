"use strict";
(() => {
  const dialog = document.querySelector("#confirmationDialog");
  const title = document.querySelector("#confirmationTitle");
  const message = document.querySelector("#confirmationMessage");
  const cancel = document.querySelector("#confirmationCancel");
  const accept = document.querySelector("#confirmationAccept");
  const queue = [];
  let active = null;

  if (!dialog || !title || !message || !cancel || !accept || typeof dialog.showModal !== "function") {
    window.CompanionConfirm = () => Promise.resolve(false);
    return;
  }

  function showNext() {
    if (active || !queue.length) return;
    active = queue.shift();
    title.textContent = active.options.title;
    message.textContent = active.options.message;
    cancel.textContent = active.options.cancelText;
    accept.textContent = active.options.confirmText;
    dialog.dataset.intent = active.options.danger ? "danger" : "normal";
    dialog.showModal();
    cancel.focus({preventScroll: true});
  }

  function finish(confirmed) {
    if (!active) return;
    const request = active;
    active = null;
    dialog.close(confirmed ? "confirm" : "cancel");
    request.resolve(confirmed);
    Promise.resolve().then(showNext);
  }

  window.CompanionConfirm = request => {
    const options = typeof request === "string" ? {message: request} : request || {};
    const content = typeof options.message === "string" ? options.message.trim() : "";
    if (!content) return Promise.resolve(false);
    return new Promise(resolve => {
      queue.push({
        options: {
          title: typeof options.title === "string" && options.title.trim() ? options.title.trim() : "请确认此操作",
          message: content,
          confirmText: typeof options.confirmText === "string" && options.confirmText.trim() ? options.confirmText.trim() : "确认",
          cancelText: typeof options.cancelText === "string" && options.cancelText.trim() ? options.cancelText.trim() : "取消",
          danger: options.danger === true,
        },
        resolve,
      });
      showNext();
    });
  };

  cancel.addEventListener("click", () => finish(false));
  accept.addEventListener("click", () => finish(true));
  dialog.addEventListener("cancel", event => {
    event.preventDefault();
    finish(false);
  });
  dialog.addEventListener("close", () => {
    if (active) finish(false);
  });
  dialog.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right
        || event.clientY < bounds.top || event.clientY > bounds.bottom) finish(false);
  });
})();
