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
    note: "仅人工采纳的规则用于对话。",
    labels: {
      group_learning_enabled: "学习群聊表达",
      window_hours: "取样窗口（小时）",
      sample_limit: "单批取样条数",
      min_samples: "最低样本数",
      sample_chars: "单条样本字符上限",
      rules_per_turn: "每轮注入规则数",
      payload_chars: "规则总字符上限",
      rotation_candidate_limit: "轮换候选池大小",
      rotation_decay_hours: "用后降权时长（小时）",
      scan_interval_minutes: "学习间隔（分钟）",
    },
    helps: {
      group_learning_enabled: "开启后按群取样 Bot 自己在该群已送达的回复；学到的规则只注入该群，默认关闭。",
      window_hours: "只看这段时间内已确认送达的回复。",
      sample_limit: "每次学习最多取多少条回复作为样本，不能小于最低样本数。",
      min_samples: "少于这个数量就不学习，避免用少量样本推断习惯。",
      sample_chars: "超出的部分会截断，避免一条长回复占满整批样本。",
      rules_per_turn: "一次回复最多带几条已采纳的表达偏好，不能大于轮换候选池大小。",
      payload_chars: "注入内容的合计长度上限。",
      rotation_candidate_limit: "每轮从已采纳规则里抽取多少条候选，再按上限截取注入。",
      rotation_decay_hours: "刚用过的规则在这段时间内权重最低，用来让学到的规则轮流被用上；默认 336（约两周）。",
      scan_interval_minutes: "后台多久看一次有没有新的已送达回复可以学。",
    },
    order: ["group_learning_enabled", "window_hours", "sample_limit", "min_samples", "sample_chars",
            "rules_per_turn", "payload_chars", "rotation_candidate_limit", "rotation_decay_hours",
            "scan_interval_minutes"],
  };

  /* 这一分区不再自带错误码表：它的读取、保存与提示都由 workbench-page.js 的
     内核统一处理（包括表达域的 expression_settings_invalid 等码），
     重复一份只会与内核漂移。 */

  /* 组合约束（后端 ExpressionLearningSettings.__post_init__ 的同一条规则）。
     单字段的最小/最大值拦不住它，所以在派发前先在这里判。 */
  const expression_audit = values => {
    if (Number.isInteger(values.sample_limit) && Number.isInteger(values.min_samples)
        && values.sample_limit < values.min_samples) return "expression_settings_invalid";
    if (Number.isInteger(values.rotation_candidate_limit) && Number.isInteger(values.rules_per_turn)
        && values.rotation_candidate_limit < values.rules_per_turn) return "expression_settings_invalid";
    return null;
  };

  /* 这一分区挂在 reply 路由族下（PREFIX = .../reply，路由是 PREFIX + "/expression"），
     不是 config 族。 */
  function endpointFor(product) {
    const reply = product.role()?.reply_api;
    if (typeof reply !== "string" || !reply.startsWith(PREFIX) || !reply.endsWith("/reply")) return null;
    return reply + "/expression";
  }

  let host = null, instance = null;

  function unmount() {
    if (instance) instance.unmount();
    if (host) host.textContent = "";
    instance = null; host = null;
  }

  function mount(element) {
    const root = element;
    unmount();
    if (!root) return;
    host = root;
    const product = window.CompanionProduct;
    if (!product?.hosted?.()) {
      root.innerHTML = '<div class="wb-notice">请从 AstrBot 打开陪伴小屋，连接 V2 运行实例后调整取样与注入上限。</div>';
      return;
    }
    const endpoint = endpointFor(product);
    if (!endpoint || !product.identity?.()?.operator_id) {
      root.innerHTML = '<div class="wb-notice is-error">当前对象没有可用的表达学习工作区。请先选择已初始化的私聊对象和角色。</div>';
      return;
    }
    if (!window.CompanionWorkbench?.create) {
      root.innerHTML = '<div class="wb-notice is-error">配置工作台未加载，无法编辑表达学习设置。</div>';
      return;
    }
    /* 不再自己加类：挂载点由 app.js 给定，工作台自己会渲染 .wb 结构。 */
    instance = window.CompanionWorkbench.create({
      group: GROUP,
      title: spec.title,
      note: spec.note,
      labels: spec.labels,
      helps: spec.helps,
      order: spec.order,
      endpoint,
      /* 组合约束（如 单批取样条数 ≥ 最低样本数）不是单字段范围能表达的，
         在派发前由这里拦下。 */
      audit: expression_audit,
      mount: () => root,
    });
    instance.mount();
  }

  return {mount, unmount, fields: spec.labels, get state() { return {instance}; }};
})();
