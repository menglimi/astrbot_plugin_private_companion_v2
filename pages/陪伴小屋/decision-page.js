"use strict";
window.CompanionDecisionPage = (() => {
  let root = null;

  function render(groupSettingsMarkup = "") {
    if (!root) return;
    root.innerHTML = `<div class="decision-page">
      <div id="perceptionOverviewWorkspace" class="perception-overview-workspace" aria-label="当前对话可用信息"></div>
      ${groupSettingsMarkup}
    </div>`;
  }

  function mount(node, options = {}) {
    if (!node) return;
    if (root === node) {
      render(options.groupSettingsMarkup || "");
      return;
    }
    unmount();
    root = node;
    render(options.groupSettingsMarkup || "");
  }

  function unmount() { root = null; }

  return {mount, unmount};
})();
