/* 表达学习的薄适配层。
   此前这里自带一套字段渲染、草稿存储、幂等重试与版本冲突处理；这些现在归
   workbench-page.js 统一负责，本文件只声明「标题 / 说明 / 字段顺序 / 文案」
   与这个分区独有的组合约束。

   挂载由 app.js 传入当前目标的 scopeKind 与 scopeKey，工作台按该范围读取。

   注意：这一分区的读取走 reply 路由族（{reply_api}/expression），
   返回值也是扁平的 {settings, edit_token, ...}，不带外层 sections——
   工作台两种形状都认，所以不需要为它改接口。 */
"use strict";
window.CompanionExpressionLearningPage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion/";
  const SPECS = {
    private: {group:"expression.learning.private", title:"私聊学习开关",
      labels:{private_learning_enabled:"允许从此用户的私聊中学习"},
      sections:[{id:"private",title:"私聊学习",fields:["private_learning_enabled"]}],
      order:["private_learning_enabled"]},
    group: {group:"expression.learning.group", title:"群聊学习设置",
      labels:{group_learning_enabled:"启用本群表达学习",group_member_mode:"学习成员范围",
        group_member_ids:"指定成员账号"},
      sections:[{id:"group",title:"本群学习",fields:["group_learning_enabled","group_member_mode","group_member_ids"]}],
      order:["group_learning_enabled","group_member_mode","group_member_ids"]},
  };

  /* 这一分区挂在 reply 路由族下（PREFIX = .../reply，路由是 PREFIX + "/expression"），
     不是 config 族。 */
  function endpointFor(product, selectedReplyApi = "") {
    const reply = selectedReplyApi || product.role()?.reply_api;
    if (typeof reply !== "string" || !reply.startsWith(PREFIX) || !reply.endsWith("/reply")) return null;
    return reply + "/expression";
  }

  let host = null, instance = null;

  function unmount() {
    if (instance) instance.unmount();
    if (host) host.textContent = "";
    instance = null; host = null;
  }

  function mount(element, options = {}) {
    const root = element;
    unmount();
    if (!root) return;
    host = root;
    const product = window.CompanionProduct;
    if (!product?.hosted?.()) {
      root.innerHTML = '<div class="wb-notice" role="status">角色数据尚未加载，请重新读取。</div>';
      return;
    }
    const endpoint = endpointFor(product, options.replyApi);
    const spec = SPECS[options.scopeKind];
    if (!spec) {
      root.innerHTML = '<div class="wb-notice" role="status">请选择私聊用户或群聊范围。</div>';
      return;
    }
    if (!endpoint || !product.identity?.()?.operator_id) {
      root.innerHTML = '<div class="wb-notice is-error">当前对象没有可用的表达学习工作区。</div>';
      return;
    }
    if (!window.CompanionWorkbench?.create) {
      root.innerHTML = '<div class="wb-notice is-error">配置工作台未加载，无法编辑表达学习设置。</div>';
      return;
    }
    /* 不再自己加类：挂载点由 app.js 给定，工作台自己会渲染 .wb 结构。 */
    let lastToken = null;
    instance = window.CompanionWorkbench.create({
      group: spec.group,
      title: spec.title,
      note: spec.note,
      labels: spec.labels,
      helps: {},
      choices: {group_member_mode: {all: "全部群成员", selected: "指定成员"}},
      sections: spec.sections,
      presentation: "journal",
      navigationLimit: 0,
      order: spec.order,
      endpoint,
      scopeKey: options.scopeKey,
      onStatus: value => {
        const changed = lastToken !== null && lastToken !== value.edit_token;
        lastToken = value.edit_token;
        if (changed && typeof CustomEvent === "function") window.dispatchEvent?.(new CustomEvent(
          "companion-workbench-saved", {detail:{group:spec.group, scopeKey:options.scopeKey}}));
      },
      mount: () => root,
    });
    instance.mount();
  }

  return {mount, unmount, get state() { return {instance}; }};
})();
