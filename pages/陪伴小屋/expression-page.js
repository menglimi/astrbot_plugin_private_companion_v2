/* 表达学习的薄适配层。
   此前这里自带一套字段渲染、草稿存储、幂等重试与版本冲突处理；这些现在归
   workbench-page.js 统一负责，本文件只声明「标题 / 说明 / 字段顺序 / 文案」
   与这个分区独有的组合约束。

   接口仍是 mount(element) + unmount()，app.js 无需改动。

   注意：这一分区的读取走 reply 路由族（{reply_api}/expression），
   返回值也是扁平的 {settings, edit_token, ...}，不带外层 sections——
   工作台两种形状都认，所以不需要为它改接口。 */
"use strict";
window.CompanionExpressionLearningPage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2/";
  const GROUP = "expression.learning";

  /* 每个字段：标签与帮助。范围不在这里声明——它由后端下发的
     FieldDefinition 契约决定（expression/configuration.py 的 LIMITS），
     避免页面写死一份会与校验器漂移的副本。 */
  const spec = {
    title: "表达学习",
    note: "",
    labels: {
      private_learning_enabled: "私聊表达学习",
      group_learning_enabled: "群聊表达学习",
      window_hours: "采样回看窗口 / 小时",
      sample_limit: "单次采样上限 / 条",
      min_samples: "私聊最少样本数 / 条",
      group_min_samples: "群聊最少样本数 / 条",
      sample_chars: "单条样本最长 / 字",
      active_signal_limit: "待审与启用规则上限 / 条",
      rules_per_turn: "每轮注入信号数 / 条",
      payload_chars: "信号负载上限 / 字",
      rotation_candidate_limit: "轮换候选上限 / 条",
      rotation_decay_hours: "刚注入的轮换衰减 / 小时",
      scan_interval_minutes: "扫描间隔 / 分钟",
      learning_mode: "学习强度",
      private_application_enabled: "私聊应用规则",
      group_application_enabled: "群聊应用规则",
      sample_review_enabled: "原始素材人工审核",
      style_review_enabled: "发送前表达复核",
      group_daily_batch_limit: "群聊每日批次上限",
      group_new_messages: "群聊新增消息门槛 / 条",
      group_member_mode: "群聊学习来源",
      group_member_ids: "指定群成员账号 / 逗号分隔",
    },
    helps: {
      private_learning_enabled: "开启后从当前私聊对象的消息学习，并且只在这个私聊中使用规则。",
      group_learning_enabled: "开启后从当前群聊成员的消息学习，并且只在这个群中使用规则；默认关闭。",
      window_hours: "只读取这段时间内仍然有效的会话消息。",
      sample_limit: "每次学习最多读取多少条消息，不能小于最低样本数。",
      min_samples: "私聊样本数量门槛。",
      group_min_samples: "群聊样本数量门槛。",
      sample_chars: "超出的部分会截断，避免一条长回复占满整批样本。",
      active_signal_limit: "待审和启用规则共用此上限；历史记录不会自动删除。",
      rules_per_turn: "一次回复最多带几条已采纳的表达偏好，不能大于轮换候选池大小。",
      payload_chars: "注入内容的合计长度上限。",
      rotation_candidate_limit: "每轮从已采纳规则里抽取多少条候选，再按上限截取注入。",
      rotation_decay_hours: "刚用过的规则在这段时间内权重最低，用来让学到的规则轮流被用上；默认 336（约两周）。",
      scan_interval_minutes: "后台检查新消息的间隔。",
    },
    sections: [
      {id: "sources", title: "学习来源",
        fields: ["learning_mode", "private_learning_enabled", "group_learning_enabled", "group_member_mode", "group_member_ids", "sample_review_enabled"]},
      {id: "application", title: "表达应用",
        fields: ["private_application_enabled", "group_application_enabled", "style_review_enabled", "rules_per_turn", "payload_chars"]},
      {id: "sampling", title: "采样与频率",
        fields: ["window_hours", "sample_limit", "min_samples", "group_min_samples", "sample_chars", "scan_interval_minutes", "group_daily_batch_limit", "group_new_messages"]},
      {id: "injection", title: "规则容量与轮换",
        fields: ["active_signal_limit", "rotation_candidate_limit", "rotation_decay_hours"]},
    ],
    order: ["private_learning_enabled", "group_learning_enabled", "window_hours", "sample_limit", "min_samples", "group_min_samples", "sample_chars", "scan_interval_minutes",
            "active_signal_limit", "rules_per_turn", "payload_chars", "rotation_candidate_limit", "rotation_decay_hours",
            "learning_mode", "private_application_enabled", "group_application_enabled", "sample_review_enabled", "style_review_enabled",
            "group_daily_batch_limit", "group_new_messages", "group_member_mode", "group_member_ids",
    ],
  };

  /* 这一分区不再自带错误码表：它的读取、保存与提示都由 workbench-page.js 的
     内核统一处理（包括表达域的 expression_settings_invalid 等码），
     重复一份只会与内核漂移。 */

  /* 组合约束（后端 ExpressionLearningSettings.__post_init__ 的同一条规则）。
     单字段的最小/最大值拦不住它，所以在派发前先在这里判。 */
  const expression_audit = values => {
    if (Number.isInteger(values.sample_limit) && Number.isInteger(values.min_samples)
        && values.sample_limit < values.min_samples) return "expression_settings_invalid";
    if (Number.isInteger(values.sample_limit) && Number.isInteger(values.group_min_samples)
        && values.sample_limit < values.group_min_samples) return "expression_settings_invalid";
    if (Number.isInteger(values.rotation_candidate_limit) && Number.isInteger(values.rules_per_turn)
        && values.rotation_candidate_limit < values.rules_per_turn) return "expression_settings_invalid";
    return null;
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
      group: GROUP,
      title: spec.title,
      note: spec.note,
      labels: spec.labels,
      helps: {},
      choices: {learning_mode: {light: "轻量", balanced: "均衡", aggressive: "深入"},
                group_member_mode: {all: "全部群成员", selected: "指定群成员"}},
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
          "companion-workbench-saved", {detail:{group:GROUP, scopeKey:options.scopeKey}}));
      },
      /* 组合约束（如 单批取样条数 ≥ 最低样本数）不是单字段范围能表达的，
         在派发前由这里拦下。 */
      audit: expression_audit,
      mount: () => root,
    });
    instance.mount();
  }

  return {mount, unmount, fields: spec.labels, get state() { return {instance}; }};
})();
