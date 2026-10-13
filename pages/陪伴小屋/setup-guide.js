/* One-time V2 setup. Progress is owned by the host and survives page and plugin reloads. */
"use strict";
window.CompanionSetup = (() => {
  const PREFIX = "setup";
  const ORDER = ["binding", "model", "knowledge", "relationships", "proactive_test"];
  const LABELS = {
    binding: "核心管理员窗口",
    model: "插件模型", knowledge: "世界知识", relationships: "关系教学", proactive_test: "主动消息测试",
  };
  const ADVANCED_BLOCKS = [
    {id: "understanding", label: "回复与分段", note: "在同一处调整分段规则，并即时查看消息效果。", mount: "reply"},
    {id: "relationships", label: "人物与资料", note: "角色资料、关系资料、世界知识与新用户默认权限。",
      editors: ["role_profile", "relationship_profile", "knowledge", "private_access"],
      views: {role_profile: {presentation: "journal"}, relationship_profile: {presentation: "journal"},
        knowledge: {sectionIds: ["import", "inject"], presentation: "journal", navigationLimit: 0}}},
    {id: "life", label: "日程与作息", note: "角色日程直接在这里维护；日记例程与睡眠作息按人格资料保存。",
      mount: "state", editors: ["life"],
      views: {life: {sectionIds: ["routine", "sleep"], title: "日记例程与睡眠作息", note: "作息跟随当前人格；日程配置也对该角色的所有私聊生效。"}}},
    {id: "action", label: "主动联系", note: "设置开口许可、频率、免打扰时段和常用契机。",
      editors: ["proactive.contact"],
      views: {"proactive.contact": {sectionIds: ["master", "rhythm", "quiet", "greeting"],
        title: "主动联系常用设置", note: "按当前角色与关系生效；更细的契机仍沿用同一配置合同。"}}},
    {id: "group", label: "群聊参与", note: "群聊回应判断、氛围参考与主动插话设置。",
      mount: "decision", editors: ["group_participation"],
      views: {group_participation: {sectionIds: ["atmosphere", "denoise", "interjection"],
        title: "群聊参与方式", note: "群聊回答由本页上方的回应规则决定；这里调整群内氛围和插话。"}}},
    {id: "runtime", label: "模型路由", note: "为主动联系、日程和后台任务分配模型；日常对话仍走 AstrBot 主链。", mount: "model"},
  ];
  const $ = (selector, root = document) => root.querySelector(selector);
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const errorText = (error, fallback) => {
    const code = typeof error?.code === "string" ? error.code : typeof error?.message === "string" ? error.message : "";
    const messages = {
      dashboard_identity_required: "请从已登录的 AstrBot 管理页面打开。",
      core_access_required: "当前账号没有管理权限。",
      staging_not_initialized: "角色数据尚未就绪，请先在账号与会话中初始化。",
      staging_host_terminated: "插件已停止，请重新打开插件页面。",
      bridge_timeout: "连接超时，请重新读取；原操作结果需要核对。",
      invalid_response: "服务返回的数据不完整，请重新读取。",
      model_route_unavailable: "当前小屋角色没有可编辑的模型路由，请切换到已关联私聊的人格。",
      model_route_scope_changed: "小屋角色已经切换，请重新读取当前角色的模型路由后再保存。",
    };
    return messages[code] || (code && !/^[a-z][a-z0-9_]{2,60}$/.test(code) ? code : fallback);
  };
  const product = () => window.CompanionProduct;
  const api = (method, path, body) => product().request(method, PREFIX + path, body);
  const LEGACY_TIMEOUT_MS = 300000;
  const migrationRequest = (method, path, body) => product().request(method, path, body,
    {timeoutMs: LEGACY_TIMEOUT_MS});
  let root = null;
  let state = null;
  let busy = false;
  let notice = "";
  let migrationProgress = "";
  let modelDraft = "";
  let modelTasks = null;
  let modelTasksStatus = "idle";
  let modelTasksError = "";
  let modelTasksPromise = null;
  let modelTasksScopeKey = null;
  let modelTaskDrafts = {};
  let profileState = null;
  let profileDraft = null;
  let profileDraftTarget = "role_profile";
  let profileFieldDrafts = {};
  let profileSelected = new Set();
  let profileSupplement = {role_profile: "", relationship_profile: ""};
  let profileOverwrite = false;
  let profileNotes = [];
  let proactiveOptIn = false;
  let proactiveWatcher = false;
  let legacyTargetId = "";
  let legacyRoleId = "";
  let legacyRootDraft = "";
  let legacyConfigScope = "proactive";
  let legacyApi = "";
  let legacyFinding = null;
  let legacyPlan = null;
  let legacyResult = null;
  let legacyDataPlan = null;
  let legacyDataResult = null;
  let legacyDataError = "";
  let legacyDataGroupId = "";
  let legacyDataPersonaId = "";
  let legacyGroupTargetId = "";
  let legacyGroupRoleId = "";
  let legacyGroupPlan = null;
  let legacyGroupResult = null;
  let legacyGroupError = "";
  let legacyGroupImportNetwork = true;
  let legacyGroupImportWorldbook = true;
  let legacyGroupConfirmMapping = false;
  let legacyGroupConfirmMemberIds = false;
  let legacyPersonaMappings = new Map();
  let legacyPersonaDestinationSequence = 0;
  let legacyPersonaBatchError = "";
  let legacyPersonaBatchProgress = "";
  let legacyImportReactions = true;
  let legacyImportGroupNetwork = false;
  let legacyImportWorldbook = false;
  let legacyImportReferenceImages = false;
  let legacyImportWardrobeItems = false;
  let legacyConfirmReferencePersonaMapping = false;
  let legacyImportArchive = true;
  let legacyImportMemoryDatabase = true;
  let legacyMemoryOwnerIds = new Set();
  let legacyMemoryGroupMappings = new Map();
  let legacyMemoryGroupMappingSeeded = false;
  let legacyMemoryPlanDirty = false;
  let legacyConfirmMemoryMapping = false;
  const MAX_LEGACY_MEMORY_OWNER_SELECTION = 128;
  let legacyConfirmMemberIds = false;
  let legacyImportJournals = false;
  let legacyConfirmPersonaMapping = false;
  let legacyError = "";
  let advancedOpen = false;
  let advancedBlock = "understanding";
  let quickEditor = null;
  let migrationOnly = false;
  let generation = 0;

  function renderAdvanced() {
    const current = ADVANCED_BLOCKS.find(item => item.id === advancedBlock) || ADVANCED_BLOCKS[0];
    const tabs = ADVANCED_BLOCKS.map(item => `<button type="button" class="setup-advanced-tab ${item.id === current.id ? "active" : ""}" data-setup-advanced-block="${item.id}" aria-pressed="${item.id === current.id}">${item.label}</button>`).join("");
    return `<div class="setup-shell setup-complete-shell setup-advanced-shell">
      <header class="setup-header"><div><span class="setup-kicker">开始使用</span><h2>快速配置</h2></div><button type="button" class="button" data-setup-action="advanced-close">返回开始使用</button></header>
      <nav class="setup-advanced-tabs" aria-label="快速配置分区">${tabs}</nav>
      <div class="setup-advanced-content"><p class="setup-advanced-note">${current.note}</p>
        <section class="setup-advanced-section"><h3>${current.label}</h3>
          ${current.mount === "model" ? renderQuickModels() : ""}
          <div id="setupQuickReplyHost" class="setup-inline-component" ${current.mount === "reply" ? "" : "hidden"}></div>
          <div id="setupQuickDecisionHost" class="setup-inline-component" ${current.mount === "decision" ? "" : "hidden"}></div>
          <div id="setupQuickStateHost" class="setup-inline-component" ${current.mount === "state" ? "" : "hidden"}></div>
          <div id="setupAdvancedEditorHost" class="setup-inline-editor" ${current.editors?.length ? "" : "hidden"}></div>
        </section>
      </div>
    </div>`;
  }

  function renderQuickModels() {
    syncModelTasksScope();
    const providers = Array.isArray(state?.model?.providers) ? state.model.providers : [];
    const providerId = modelDraft || state?.model?.provider_id || "";
    const canSetInitialProvider = state?.step === "model" && !state?.ready;
    const tasks = (modelTasks?.tasks || []).filter(task =>
      ["proactive.compose", "calendar.plan", "role.state.maintain", "role.self_review"].includes(task.kind));
    const taskProviders = Array.isArray(modelTasks?.providers) ? modelTasks.providers : [];
    const taskMarkup = tasks.map(task => {
      const draft = modelTaskDrafts[task.kind] || {};
      const provider = draft.provider ?? task.fields.provider.value;
      const fallback = draft.fallback ?? task.fields.fallback.value;
      const choices = taskProviders.filter(item => task.capabilities.every(capability => item.capabilities.includes(capability)));
      return `<details class="setup-task-route"><summary><strong>${escape(taskLabel(task.kind))}</strong><small>${escape(task.kind)}</small></summary><div class="setup-task-route-fields"><label><span>主模型</span><select data-setup-model-task="${escape(task.kind)}" data-setup-model-field="provider" ${busy || !choices.length ? "disabled" : ""}>${choices.map(item => `<option value="${escape(item.id)}" ${provider === item.id ? "selected" : ""}>${escape(item.name || item.id)}</option>`).join("")}</select></label><label><span>备用模型</span><select data-setup-model-task="${escape(task.kind)}" data-setup-model-field="fallback" ${busy || !choices.length ? "disabled" : ""}><option value="">不设置</option>${choices.filter(item => item.id !== provider).map(item => `<option value="${escape(item.id)}" ${fallback === item.id ? "selected" : ""}>${escape(item.name || item.id)}</option>`).join("")}</select></label>${button(`save-task:${task.kind}`, "保存", {disabled: !choices.length})}</div></details>`;
    }).join("");
    const providerMarkup = canSetInitialProvider
      ? providers.length ? `<label class="setup-model-field"><span>陪伴通用模型</span><select name="setup-provider" ${busy ? "disabled" : ""}><option value="">选择模型</option>${providers.map(item => `<option value="${escape(item.id)}" ${providerId === item.id ? "selected" : ""}>${escape(item.name)} · ${escape(item.id)}</option>`).join("")}</select></label>${button("save-model", state?.prepared ? "保存通用模型" : "初始化并载入模型", {primary: true, disabled: !providerId})}`
        : `<p class="setup-inline-error">没有可用的文本模型，请先在 AstrBot 中加载 Provider 后刷新本页。</p>`
      : `<div class="setup-model-default"><span>陪伴通用模型</span><strong>${escape(providerId || "未设置")}</strong></div>`;
    const routesMarkup = modelTasksStatus === "loading"
      ? `<p class="setup-inline-loading" role="status">正在读取后台模型路由…</p>`
      : modelTasksStatus === "error"
        ? `<div class="setup-inline-error" role="alert"><span>${escape(modelTasksError || "后台模型路由暂时无法读取。")}</span>${button("retry-model-routes", "重新读取")}</div>`
        : modelTasks ? taskMarkup || `<p class="setup-inline-empty">当前没有这些后台任务的模型路由。</p>`
          : `<p class="setup-inline-loading" role="status">正在读取后台模型路由…</p>`;
    return `<div class="setup-quick-models"><p class="setup-quick-models-note">陪伴模型用于插件内部任务；日常对话回复仍跟随 AstrBot 当前人格与主链。</p>
      ${providerMarkup}
      <section class="setup-model-routes"><header><div><h4>常用后台任务</h4><p>主动联系、日程、状态与每日反思</p></div><span>${tasks.length} 项</span></header>${routesMarkup}</section>
    </div>`;
  }

  function stopQuickWorkspace() {
    quickEditor?.stop?.();
    quickEditor = null;
    window.CompanionReplyPage?.unmount?.();
    window.CompanionStatePage?.unmount?.();
  }

  function mountQuickWorkspace() {
    const block = ADVANCED_BLOCKS.find(item => item.id === advancedBlock);
    if (!block || !root) return;
    const host = selector => root.querySelector(selector);
    if (block.mount === "reply") window.CompanionReplyPage?.mount?.(host("#setupQuickReplyHost"),
      {view: "expression", expressionModule: "expression-text", section: "segment"});
    if (block.mount === "decision") window.CompanionReplyPage?.mount?.(host("#setupQuickDecisionHost"), {view: "decision"});
    if (block.mount === "state") window.CompanionStatePage?.mount?.(host("#setupQuickStateHost"), {section: "state", feature: "planning"});
    if (block.editors?.length) {
      quickEditor = window.CompanionConfigEditors?.create?.(block.editors, () => host("#setupAdvancedEditorHost"), block.views || {});
      if (quickEditor) {
        quickEditor.restore?.();
        quickEditor.paint?.();
        void quickEditor.read?.();
      } else {
        const editorHost = host("#setupAdvancedEditorHost");
        if (editorHost) editorHost.innerHTML = `<p class="setup-inline-unavailable">当前角色的设置工作台暂不可用，请重新读取后再试。</p>`;
      }
    }
    if (block.mount === "model" && state?.prepared && modelTasksStatus === "idle") void loadQuickModels();
  }

  function currentModelScopeKey() {
    const productApi = product();
    return productApi?.scopeKey?.() || productApi?.role?.()?.model_api || "";
  }

  function syncModelTasksScope(scope = currentModelScopeKey()) {
    if (scope === modelTasksScopeKey) return scope;
    modelTasksScopeKey = scope;
    modelTasks = null;
    modelTasksStatus = "idle";
    modelTasksError = "";
    modelTasksPromise = null;
    modelTaskDrafts = {};
    return scope;
  }

  function currentRoleModelRoute() {
    const productApi = product();
    const endpoint = productApi?.role?.()?.model_api;
    if (typeof endpoint !== "string" || !endpoint) {
      throw Object.assign(new Error("model_route_unavailable"), {code: "model_route_unavailable"});
    }
    const path = productApi.relative(endpoint);
    if (typeof path !== "string" || !path) {
      throw Object.assign(new Error("model_route_unavailable"), {code: "model_route_unavailable"});
    }
    return {path, scope: productApi.scopeKey?.() || endpoint};
  }

  function modelTaskPayload(response) {
    let value = response;
    for (let depth = 0; depth < 3; depth += 1) {
      if (Array.isArray(value?.tasks) && Array.isArray(value?.providers)) return value;
      if (!value?.data || typeof value.data !== "object" || Array.isArray(value.data)) return null;
      value = value.data;
    }
    return null;
  }

  async function readModelTasks({force = false} = {}) {
    let route;
    try {
      route = currentRoleModelRoute();
      syncModelTasksScope(route.scope);
    } catch (error) {
      syncModelTasksScope();
      modelTasksStatus = "error";
      modelTasksError = errorText(error, "后台模型路由暂时无法读取。");
      return null;
    }
    if (modelTasksStatus === "loading" && modelTasksPromise) return modelTasksPromise;
    if (!force && modelTasksStatus === "loaded") return modelTasks;
    modelTasksStatus = "loading";
    modelTasksError = "";
    const request = (async () => {
      try {
        const result = await product().request("GET", route.path);
        if (route.scope !== currentModelScopeKey()) {
          syncModelTasksScope();
          return null;
        }
        const payload = modelTaskPayload(result);
        if (!payload) {
          throw Object.assign(new Error("invalid_response"), {code: "invalid_response"});
        }
        const names = new Map((state?.model?.providers || []).map(item => [item.id, item.name || item.id]));
        modelTasks = {...payload, providers: payload.providers.map(item => ({
          ...item, name: item.name || names.get(item.id) || item.id,
        }))};
        modelTasksStatus = "loaded";
      } catch (error) {
        if (route.scope !== currentModelScopeKey()) {
          syncModelTasksScope();
          return null;
        }
        modelTasks = null;
        modelTasksStatus = "error";
        modelTasksError = errorText(error, "后台模型路由暂时无法读取。");
      }
      return modelTasks;
    })();
    modelTasksPromise = request;
    try { return await request; }
    finally { if (modelTasksPromise === request) modelTasksPromise = null; }
  }

  async function loadQuickModels() {
    syncModelTasksScope();
    if (modelTasksStatus === "loading") return modelTasksPromise;
    await readModelTasks();
    if (root && advancedOpen && advancedBlock === "runtime") render();
  }

  async function retryQuickModels() {
    syncModelTasksScope();
    modelTasksStatus = "idle";
    modelTasksError = "";
    await loadQuickModels();
  }

  async function refreshModelTasks() {
    try {
      await readModelTasks({force: true});
      if (modelTasksStatus === "error") return modelTasksError;
    } catch (error) {
      modelTasks = null;
      modelTasksStatus = "error";
      modelTasksError = errorText(error, "后台模型路由暂时无法读取。");
      return modelTasksError;
    }
    return "";
  }

  function progress() {
    const done = new Set(state?.completed || []);
    const skipped = new Set(state?.skipped || []);
    const bindingDone = Boolean(state?.binding_confirmed);
    const prepared = Boolean(state?.prepared);
    return ORDER.map(id => {
      const complete = id === "binding" ? bindingDone
        : id === "proactive_test" ? Boolean(state?.ready)
        : done.has(id) || skipped.has(id);
      return {id, label: LABELS[id], complete};
    });
  }

  function stepIndex(step) {
    const index = ORDER.indexOf(step);
    return index < 0 ? 0 : index;
  }

  function renderRail(step) {
    return `<ol class="setup-progress" aria-label="首次连接进度">${progress().map((item, index) => `
      <li class="${item.complete ? "complete" : ""} ${item.id === step ? "current" : ""}">
        <span class="setup-progress-marker">${item.complete ? "✓" : String(index + 1).padStart(2, "0")}</span>
        <span>${escape(item.label)}</span>
      </li>`).join("")}</ol>`;
  }

  function noticeMarkup() {
    const text = notice || migrationProgress;
    if (!text) return "";
    return `<p class="setup-notice" role="status">${escape(text)}</p>`;
  }

  function connectionDiagnostic() {
    const failure = state?.host?.last_failure;
    const message = {staging_profile_conflict: "固定运行档的绑定条件发生变化，请检查 Bot 账号、私聊对象和人格。模型参数变化不会阻止连接。",
      host_binding_changed: "Bot 账号、私聊对象或人格绑定发生变化，请重新核对当前窗口。"}[failure?.code];
    return message ? `<p class="setup-inline-error" role="alert">${escape(message)}</p>` : "";
  }

  function button(action, label, {primary = false, disabled = false} = {}) {
    return `<button type="button" class="button${primary ? " primary" : ""}" data-setup-action="${escape(action)}" ${disabled || busy ? "disabled" : ""}>${escape(label)}</button>`;
  }

  function homeButton(label, primary = false) {
    return `<button type="button" class="button${primary ? " primary" : ""}" data-go="life">${escape(label)}</button>`;
  }

  const legacyTargetLabel = item => product()?.targetLabel?.(item) || item.display_name || "当前会话对象";
  const legacyRoleLabel = (item,index) => product()?.roleLabel?.(item,index) || item.role_name || item.persona_ids?.filter(Boolean).join(" / ") || "当前角色";
  const legacyAccountLabel = item => product()?.accountLabel?.(item) || item.account_name || "当前账号";
  const legacySources = {"private.host_configuration": "陪伴插件配置", "private.core_profiles": "人物与关系档案",
    "private.group_relationship_graph": "群成员互动图", "private.reaction_assets": "表情素材",
    "memory.timeline_and_governance": "记忆与历史记录", "private.work_and_delivery": "任务与投递记录",
    "private.world_assets": "世界与相册素材", "content.creative_projects": "创作项目",
    "image.generation_state": "图片生成记录", "reality.device_and_observations": "设备与观察记录",
     "extensions.session_and_media": "拓展会话与媒体"};
  const PROFILE_LABELS = {
    name:"姓名", species:"种族", birthday:"生日", age:"年龄感", gender:"性别", occupation:"职业 / 身份",
    identity:"身份经历", appearance_points:"外貌识别点", hair:"发型与发色", eyes:"眼部特征", clothing:"服饰风格",
    image_identity_hint:"图像识别线索", appearance:"外貌补充", personality:"性格", first_person:"自称与代词",
    speech_style:"说话方式", emotional_style:"情绪表达", social_distance:"社交距离", reaction_patterns:"典型反应",
    voice_examples:"口吻示例", signature_phrases:"标志性表达", daily_habits:"日常习惯", key_lore:"关键设定",
    character_extra:"其他角色补充", motivations:"价值与目标", core_values:"重视的事", desire:"长期目标", hobbies:"爱好",
    boundaries:"互动边界", taboos:"禁忌", world_name:"所处世界", era:"时代背景", tone:"世界基调", rules:"世界规则",
    scenes:"主要场景", network:"世界观关系网", world_extra:"其他世界设定", world:"世界设定补充",
    platform_group_chat:"群聊称呼", platform_screen:"识屏称呼", platform_bilibili:"视频站称呼",
    platform_qzone:"动态墙称呼", platform_library:"资料柜称呼", platform_names:"平台称呼补充",
    world_adaptation_mode:"世界观适配模式", world_adaptation:"世界观适配指引",
    default_nickname:"对用户的称呼", user_gender:"用户性别", user_birthday:"用户生日", user_occupation:"用户职业",
    role_relation:"用户与角色的关系", interaction:"相处方式", extra:"其他关系补充",
  };
  const TASK_LABELS = {
    "conversation.reply":"对话回复", "proactive.compose":"主动联系", "proactive.judge":"主动内容审核",
    "memory.reflect":"记忆整理", "role.state.maintain":"角色状态", "calendar.plan":"日程规划",
    "role.growth.progress":"成长进展", "role.self_review":"自我复盘", "role.expression.learn":"表达学习",
    "role.expression.review":"回复表达复核", "role.expression.contact_review":"主动表达复核",
    "role.reading.consume":"阅读理解", "image.review":"图片审核", "context.caption":"图片描述",
    "screen.interpret":"识屏理解", "content.authoring":"内容创作", "role.journal":"日记与梦境",
  };

  function operationKey(prefix) {
    return window.crypto?.randomUUID?.() || `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  function taskLabel(kind) {
    if (TASK_LABELS[kind]) return TASK_LABELS[kind];
    return kind.split(".").map(part => part.replace(/_/g, " ")).join(" · ");
  }

  function legacyChoices() {
    const targets = (product()?.targets?.() || []).filter(target =>
      (target.roles || []).some(role => role.legacy_api));
    const target = targets.find(item => item.target_id === legacyTargetId) || null;
    const roles = target?.roles?.filter(role => role.legacy_api) || [];
    const role = roles.find(item => item.role_id === legacyRoleId) || null;
    return {targets, target, roles, role};
  }

  function legacyAddress() {
    const role = legacyChoices().role;
    return role?.legacy_api ? product().relative(role.legacy_api) : "";
  }

  function legacySelection() {
    const choices = legacyChoices();
    return {...choices, api: legacyAddress()};
  }

  function legacyRoute(suffix = "") {
    return `${legacyApi}${suffix}`;
  }

  function legacyQuery() {
    const query = {configuration_scope: legacyConfigScope};
    const root = legacyRootDraft.trim();
    if (root) query.v1_root = root;
    return query;
  }

  function legacyDataQuery() {
    const query = {};
    const root = legacyRootDraft.trim();
    if (root) query.v1_root = root;
    if (legacyDataGroupId) query.source_group_id = legacyDataGroupId;
    if (legacyDataPersonaId) query.source_persona_id = legacyDataPersonaId;
    if (legacyMemoryOwnerIds.size) query.memory_owner_ids = [...legacyMemoryOwnerIds].sort().join(",");
    if (legacyMemoryGroupMappings.size) query.memory_group_mappings = JSON.stringify(
      [...legacyMemoryGroupMappings.entries()].sort(([left], [right]) => left.localeCompare(right))
        .map(([owner_id, target]) => ({owner_id, target_id: target.target_id, role_id: target.role_id})));
    query.reference_slots_available = "24";
    query.reference_bytes_available = String(24 * 20 * 1024 * 1024);
    query.wardrobe_slots_available = "24";
    return query;
  }

  function seedMemoryGroupMappings(data) {
    if (legacyMemoryGroupMappingSeeded) return;
    legacyMemoryGroupMappingSeeded = true;
    let added = false;
    const owners = data?.memory_database?.identity_inventory?.owners || [];
    const targets = data?.memory_database?.group_targets || [];
    for (const owner of owners.filter(item => item.source?.scope === "group")) {
      const source = owner.source;
      const exact = targets.filter(target => target.group_id === source.group_id
        && target.platform_id === source.platform && target.bot_id === source.bot_id);
      const sameNumber = exact.length ? exact : targets.filter(target => target.group_id === source.group_id);
      const choices = sameNumber.flatMap(target => {
        const matchingRoles = target.roles.filter(role => role.persona_ids?.includes(source.persona_id));
        const roles = matchingRoles.length ? matchingRoles : target.roles.length === 1 ? target.roles : [];
        return roles.map(role => ({target_id: target.target_id, role_id: role.role_id}));
      });
      if (choices.length === 1) {
        legacyMemoryGroupMappings.set(owner.owner_id, choices[0]);
        added = true;
      }
    }
    if (added) {
      legacyMemoryPlanDirty = true;
      legacyConfirmMemoryMapping = false;
    }
  }

  function legacyArchiveCanApply(archive) {
    return ["ready", "incomplete"].includes(archive?.state)
      && (Number(archive.file_count) > 0 || Number(archive.excluded_count) > 0);
  }

  function legacyMemoryArchiveCanApply(archive) {
    return ["ready", "incomplete"].includes(archive?.state)
      && ((Array.isArray(archive.assets) && archive.assets.length > 0)
        || Number(archive.excluded_count) > 0);
  }

  function legacyPersonaQuery(personaId) {
    const query = {};
    const root = legacyRootDraft.trim();
    if (root) query.v1_root = root;
    if (personaId) query.source_persona_id = personaId;
    return query;
  }

  function legacyPersonaTargets() {
    return (product()?.targets?.() || []).filter(target => target.scope_kind !== "group"
      && Array.isArray(target.roles) && target.roles.some(role => role.legacy_api));
  }

  function newLegacyPersonaDestination() {
    legacyPersonaDestinationSequence += 1;
    return {destination_id: `destination-${legacyPersonaDestinationSequence}`,
      target_id: "", role_id: "", include_reactions: true, include_worldbook: false,
      include_journals: false, confirm_member_ids: false, confirm_persona_mapping: false,
      include_reference_images: false, include_wardrobe_items: false,
      confirm_reference_persona_mapping: false,
      plan: null, result: null, status: "unmapped", error: ""};
  }

  function legacyPersonaRole(destination) {
    const target = legacyPersonaTargets().find(item => item.target_id === destination.target_id);
    return target?.roles?.find(role => role.role_id === destination.role_id && role.legacy_api) || null;
  }

  function legacyPersonaAssignments(personas) {
    return (personas || []).flatMap(persona => {
      const sourceId = persona.persona_id || "";
      const mapping = legacyPersonaMappings.get(sourceId);
      if (!mapping || mapping.skip) return [];
      return (mapping.destinations || []).map(destination => ({persona, sourceId, mapping, destination}));
    });
  }

  function legacyPersonaRoleTaken(targetId, roleId, sourceId, destinationId) {
    if (!targetId || !roleId) return false;
    for (const [otherSourceId, mapping] of legacyPersonaMappings) {
      if (mapping.skip) continue;
      for (const destination of mapping.destinations || []) {
        if (otherSourceId === sourceId && destination.destination_id === destinationId) continue;
        if (destination.target_id === targetId && destination.role_id === roleId) return true;
      }
    }
    return false;
  }

  function hasDuplicateLegacyPersonaRoles(assignments) {
    const seen = new Set();
    for (const {destination} of assignments) {
      if (!destination.target_id || !destination.role_id) continue;
      const key = `${destination.target_id}\u0000${destination.role_id}`;
      if (seen.has(key)) return true;
      seen.add(key);
    }
    return false;
  }

  function syncLegacyPersonaMappings(personas) {
    const next = new Map();
    for (const persona of personas || []) {
      if (persona.state !== "ready") continue;
      const sourceId = persona.persona_id || "";
      const previous = legacyPersonaMappings.get(sourceId) || {};
      const destinations = Array.isArray(previous.destinations) ? previous.destinations
        : (previous.target_id || previous.role_id ? [{...newLegacyPersonaDestination(),
          target_id: previous.target_id || "", role_id: previous.role_id || "",
          include_reactions: previous.include_reactions !== false,
          include_worldbook: previous.include_worldbook === true,
          include_journals: previous.include_journals === true,
          confirm_member_ids: previous.confirm_member_ids === true,
          confirm_persona_mapping: previous.confirm_persona_mapping === true,
          include_reference_images: previous.include_reference_images === true,
          include_wardrobe_items: previous.include_wardrobe_items === true,
          confirm_reference_persona_mapping: previous.confirm_reference_persona_mapping === true,
          plan: previous.plan || null, result: previous.result || null,
          status: previous.status || "unmapped", error: previous.error || ""}] : []);
      next.set(sourceId, {
        source_persona_id: sourceId,
        skip: previous.skip === true,
        destinations,
      });
    }
    legacyPersonaMappings = next;
  }

  function legacyPersonaBatchCanApply(destination) {
    const plan = destination?.plan;
    if (!plan?.plan_token || !legacyPersonaRole(destination)) return false;
    const reactions = plan.reaction_assets || {};
    const journals = plan.journals || {};
    const worldbook = plan.worldbook || {};
    const references = plan.reference_images || {};
    const wardrobe = plan.wardrobe_items || {};
    const worldbookReady = destination.include_worldbook && (
      (Number(worldbook.general_count) > 0 && !worldbook.base_entries_matches)
      || (destination.confirm_member_ids && Number(worldbook.member_count) > 0
        && !worldbook.base_members_matches));
    const referencesReady = (destination.include_reference_images && Number(references.batch_count) > 0)
      || (destination.include_wardrobe_items && Number(wardrobe.batch_count) > 0);
    return (destination.include_reactions && Number(reactions.batch_count) > 0)
      || (destination.include_journals && Number(journals.batch_count) > 0
        && destination.confirm_persona_mapping)
      || worldbookReady || (referencesReady && destination.confirm_reference_persona_mapping);
  }

  function renderLegacyPersonaBatch(personas) {
    const ready = (personas || []).filter(item => item.state === "ready");
    if (!ready.length) return "";
    syncLegacyPersonaMappings(personas);
    const targets = legacyPersonaTargets();
    const allDecided = ready.every(item => {
      const mapping = legacyPersonaMappings.get(item.persona_id || "");
      return mapping && (mapping.skip || (mapping.destinations.length > 0
        && mapping.destinations.every(destination => destination.target_id && destination.role_id
          && legacyPersonaRole(destination))));
    });
    const assignments = legacyPersonaAssignments(ready);
    const duplicates = hasDuplicateLegacyPersonaRoles(assignments);
    const canPreview = allDecided && assignments.length > 0 && !duplicates && !busy;
    const canApply = allDecided && assignments.some(item => legacyPersonaBatchCanApply(item.destination))
      && assignments.every(({destination}) => destination.plan?.plan_token && !destination.error)
      && !duplicates && !busy;
    const statusLabel = destination => ({unmapped: "待映射", mapped: "待试算", planning: "正在试算", ready: "已试算",
      applying: "正在导入", imported: "本批已完成", partial: "仍有后续批次或未导入项",
      skipped: "已明确跳过", error: "执行失败", unknown: "结果未确认", stale: "来源已变化"}[destination.status]
      || "待试算");
    const rows = (personas || []).map((persona, index) => {
      const sourceId = persona.persona_id || "";
      if (persona.state !== "ready") return `<div class="setup-legacy-persona-row is-unavailable"><strong>${escape(persona.label || "V1 人格")}</strong><span>来源状态：${escape(persona.state || "不可读取")}，不进入自动导入。</span></div>`;
      const mapping = legacyPersonaMappings.get(sourceId);
      const destinations = mapping.destinations.map((destination, destinationIndex) => {
        const target = targets.find(item => item.target_id === destination.target_id);
        const roles = target?.roles?.filter(role => role.legacy_api) || [];
        const summary = destination.plan;
        const reactionCount = Number(summary?.reaction_assets?.batch_count) || 0;
        const journalCount = Number(summary?.journals?.batch_count) || 0;
        const worldbook = summary?.worldbook || {};
        const references = summary?.reference_images || {};
        const wardrobe = summary?.wardrobe_items || {};
        const worldbookCount = (Number(worldbook.general_count) || 0) + (destination.confirm_member_ids
          ? Number(worldbook.member_count) || 0 : 0);
        const result = destination.result;
        const resultLine = result ? `最近一批：表情 ${Number(result.reaction_created) || 0} 张，日记/梦境 ${Number(result.journal_created) || 0} 条，参考图 ${Number(result.reference_images?.reference_created) || 0} 张，衣物 ${Number(result.reference_images?.wardrobe_created) || 0} 条；参考图 ${Number(result.reference_images?.reference_remaining) || 0} 张、衣物 ${Number(result.reference_images?.wardrobe_remaining) || 0} 条待继续。` : "";
        return `<div class="setup-legacy-persona-destination" data-destination-row="${escape(destination.destination_id)}">
          <div class="setup-legacy-persona-destination-head"><strong>目标映射 ${destinationIndex + 1}</strong><span>${escape(statusLabel(destination))}${destination.error ? ` · ${escape(destination.error)}` : ""}</span><button type="button" data-setup-legacy-batch-remove="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${busy ? "disabled" : ""}>移除</button></div>
          <div class="setup-legacy-persona-destination-fields">
            <label><span>V2 私聊目标</span><select data-setup-legacy-batch-target data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${mapping.skip || busy ? "disabled" : ""}><option value="">明确选择目标</option>${targets.map(item => `<option value="${escape(item.target_id)}" ${destination.target_id === item.target_id ? "selected" : ""}>${escape(legacyTargetLabel(item))} · ${escape(legacyAccountLabel(item))}</option>`).join("")}</select></label>
            <label><span>V2 角色</span><select data-setup-legacy-batch-role data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${mapping.skip || !target || busy ? "disabled" : ""}><option value="">明确选择角色</option>${roles.map((role, roleIndex) => {
              const duplicate = legacyPersonaRoleTaken(destination.target_id, role.role_id, sourceId, destination.destination_id);
              return `<option value="${escape(role.role_id)}" ${destination.role_id === role.role_id ? "selected" : ""} ${duplicate ? "disabled" : ""}>${escape(legacyRoleLabel(role, roleIndex))}${duplicate ? " · 已映射" : ""}</option>`;
            }).join("")}</select></label>
          </div>
          ${summary ? `<div class="setup-legacy-persona-options">
            <label><input type="checkbox" data-setup-legacy-batch-option="reactions" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.include_reactions ? "checked" : ""} ${!reactionCount || busy ? "disabled" : ""}><span>表情 ${reactionCount} 张</span></label>
            <label><input type="checkbox" data-setup-legacy-batch-option="worldbook" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.include_worldbook ? "checked" : ""} ${!worldbookCount || busy ? "disabled" : ""}><span>世界书 ${worldbookCount} 条</span></label>
            ${destination.include_worldbook && worldbook.requires_id_confirmation ? `<label><input type="checkbox" data-setup-legacy-batch-option="confirm-members" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.confirm_member_ids ? "checked" : ""} ${busy ? "disabled" : ""}><span>确认成员账号映射与目标平台一致</span></label>` : ""}
            <label><input type="checkbox" data-setup-legacy-batch-option="journals" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.include_journals ? "checked" : ""} ${!journalCount || busy ? "disabled" : ""}><span>日记与梦境 ${journalCount} 条</span></label>
            ${destination.include_journals && journalCount ? `<label><input type="checkbox" data-setup-legacy-batch-option="confirm-journals" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.confirm_persona_mapping ? "checked" : ""} ${busy ? "disabled" : ""}><span>确认将该 V1 人格资料归入所选角色</span></label>` : ""}
            <label><input type="checkbox" data-setup-legacy-batch-option="reference-images" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.include_reference_images ? "checked" : ""} ${!Number(references.batch_count) || busy ? "disabled" : ""}><span>参考图库 ${Number(references.batch_count) || 0} 张</span></label>
            <label><input type="checkbox" data-setup-legacy-batch-option="wardrobe-items" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.include_wardrobe_items ? "checked" : ""} ${!Number(wardrobe.batch_count) || busy ? "disabled" : ""}><span>衣柜 ${Number(wardrobe.batch_count) || 0} 件（图片 ${Number(wardrobe.image_count) || 0} 张）</span></label>
            ${(destination.include_reference_images && Number(references.batch_count) || destination.include_wardrobe_items && Number(wardrobe.batch_count)) ? `<label><input type="checkbox" data-setup-legacy-batch-option="confirm-reference-persona" data-persona-id="${escape(sourceId)}" data-destination-id="${escape(destination.destination_id)}" ${destination.confirm_reference_persona_mapping ? "checked" : ""} ${busy ? "disabled" : ""}><span>确认将该人格参考图与衣柜归入此角色</span></label>` : ""}
            ${resultLine ? `<p>${escape(resultLine)}</p>` : ""}
          </div>` : destination.status === "stale" ? `<p class="setup-legacy-persona-note">V1 来源清单在试算期间发生变化，请重新试算全部映射。</p>` : ""}
        </div>`;
      }).join("");
      return `<div class="setup-legacy-persona-row" data-persona-row="${index}">
        <div class="setup-legacy-persona-source"><strong>${escape(persona.label || (sourceId ? `V1 人格：${sourceId}` : "主角色（companions.json）"))}</strong><span>${mapping.skip ? "已明确跳过" : `${mapping.destinations.length} 个目的地`}</span></div>
        <label class="setup-legacy-persona-skip"><input type="checkbox" data-setup-legacy-batch-skip data-persona-id="${escape(sourceId)}" ${mapping.skip ? "checked" : ""} ${busy ? "disabled" : ""}><span>明确跳过此人格</span></label>
        ${mapping.skip ? "" : `<div class="setup-legacy-persona-destinations">${destinations || `<p class="setup-legacy-persona-note">尚未添加目标。不会自动复制到任何 V2 私聊。</p>`}
          <button type="button" class="button" data-setup-legacy-batch-add="${escape(sourceId)}" ${busy ? "disabled" : ""}>添加 V2 目的地</button>
        </div>`}
      </div>`;
    }).join("");
    const unready = (personas || []).filter(item => item.state !== "ready").length;
    return `<section class="setup-legacy-persona-batch">
      <h5>多人格运行资料映射</h5>
      <p>逐个人格添加 V2 私聊目标与角色，或明确跳过。每个目标单独试算；失败或结果未确认时会停止后续导入。当前支持 OneBot。${unready ? `另有 ${unready} 份来源不可读取。` : ""}</p>
      ${legacyPersonaBatchError ? `<p class="setup-inline-error">${escape(legacyPersonaBatchError)}</p>` : ""}
      ${legacyPersonaBatchProgress ? `<p class="setup-legacy-persona-progress" role="status">${escape(legacyPersonaBatchProgress)}</p>` : ""}
      ${duplicates ? `<p class="setup-inline-error">同一个 V2 私聊目标与角色只能映射一次，请先移除重复项。</p>` : ""}
      <div class="setup-legacy-persona-list">${rows}</div>
      <div class="setup-actions">${legacyButton("legacy-data-batch-plan", "试算已选择的目的地", {primary: !assignments.every(item => item.destination.plan), disabled: !canPreview})}${canApply ? legacyButton("legacy-data-batch-apply", "按目的地逐项导入", {primary: true}) : ""}</div>
    </section>`;
  }

  function legacyGroupSelection() {
    const targets = (product()?.targets?.() || []).filter(item => item.scope_kind === "group"
      && (item.roles || []).some(role => role.legacy_group_data_api));
    const target = targets.find(item => item.target_id === legacyGroupTargetId) || null;
    const roles = target?.roles?.filter(role => role.legacy_group_data_api) || [];
    const role = roles.find(item => item.role_id === legacyGroupRoleId) || null;
    const persona = (legacyDataPlan?.persona_sources || []).find(item =>
      item.persona_id === legacyDataPersonaId) || null;
    const group = (legacyDataPlan?.group_networks || []).find(item =>
      item.source_group_id === legacyDataGroupId) || null;
    const worldbookGroup = (legacyDataPlan?.worldbook?.groups || []).find(item =>
      item.source_group_id === legacyDataGroupId) || null;
    const worldbookMembers = (legacyDataPlan?.worldbook?.member_profile_groups || []).find(item =>
      item.source_group_id === legacyDataGroupId) || null;
    const api = role?.legacy_group_data_api ? product().relative(role.legacy_group_data_api) : "";
    return {targets, target, roles, role, persona, group, worldbookGroup, worldbookMembers, api};
  }

  function renderLegacyGroupMapping() {
    const choices = legacyGroupSelection();
    const counts = legacyGroupPlan?.group_worldbook || {};
    const network = legacyGroupPlan?.source_group_network;
    const canPlan = Boolean(choices.persona && legacyDataGroupId && choices.target && choices.role && !busy);
    const canApply = Boolean(legacyGroupPlan?.plan_token && choices.role && !busy
      && legacyGroupConfirmMapping
      && (legacyGroupImportNetwork && network || legacyGroupImportWorldbook
        && Number(counts.entries) + Number(counts.members) > 0 && !counts.conflict)
      && (!legacyGroupImportNetwork && !legacyGroupImportWorldbook ? false : legacyGroupConfirmMemberIds));
    return `<section class="setup-legacy-persona-batch setup-legacy-group-mapping">
      <h5>V1 群记录映射</h5>
      <p>群内互动图和群范围资料需映射到对应 V2 群。核对平台、Bot、群号和成员 ID；个人关系账户不在此处迁移。当前支持 OneBot。</p>
      <div class="setup-legacy-persona-row">
        <strong>${escape(choices.persona?.label || "先选择可读取的 V1 人格")}</strong>
        <strong>${escape(legacyDataGroupId ? `V1 群 ${legacyDataGroupId}` : "先选择 V1 群记录")}</strong>
        <label><span>V2 群目标</span><select data-setup-legacy="group-target" ${choices.targets.length && legacyDataGroupId ? "" : "disabled"}><option value="">明确选择群目标</option>${choices.targets.map(item => `<option value="${escape(item.target_id)}" ${item.target_id === legacyGroupTargetId ? "selected" : ""}>${escape(legacyTargetLabel(item))} · ${escape(legacyAccountLabel(item))}</option>`).join("")}</select></label>
        <label><span>V2 角色</span><select data-setup-legacy="group-role" ${choices.target && legacyDataGroupId ? "" : "disabled"}><option value="">明确选择角色</option>${choices.roles.map((item, index) => `<option value="${escape(item.role_id)}" ${item.role_id === legacyGroupRoleId ? "selected" : ""}>${escape(legacyRoleLabel(item, index))}</option>`).join("")}</select></label>
      </div>
      ${legacyGroupError ? `<p class="setup-inline-error">${escape(legacyGroupError)}</p>` : ""}
      ${legacyGroupPlan ? `<div class="setup-legacy-persona-result">
        <p>试算目标：${escape(legacyGroupPlan.target?.platform_id || "")} / ${escape(legacyGroupPlan.target?.account_id || "")} / 群 ${escape(legacyGroupPlan.target?.group_id || "")} · 角色 ${escape(legacyGroupPlan.target?.role_id || "")}</p>
        ${network ? `<p>V1 群成员互动图：${Number(network.member_count) || 0} 位成员 / ${Number(network.edge_count) || 0} 条互动边；超限或无效项已从导入数量中排除。</p>` : `<p>所选人格没有这条群成员互动图。</p>`}
        <p>V1 群资料：${Number(counts.entries) || 0} 条群范围知识，${Number(counts.members) || 0} 条群成员线索。${counts.conflict ? "V2 已存在其他归属的同名来源，不能覆盖。" : counts.already_present ? "内容已存在。" : ""}</p>
        ${legacyGroupResult ? `<p class="setup-recorded">${legacyGroupResult.group_network ? `群成员互动图新增 ${Number(legacyGroupResult.group_network.members_added) || 0} 位成员、${Number(legacyGroupResult.group_network.edges_added) || 0} 条边。` : ""}${legacyGroupResult.group_worldbook ? `群资料 ${legacyGroupResult.group_worldbook.state === "unchanged" ? "已存在" : "已导入"} ${Number(legacyGroupResult.group_worldbook.entries_imported) || 0} 条知识、${Number(legacyGroupResult.group_worldbook.members_imported) || 0} 条成员线索。` : ""}</p>` : ""}
      </div>` : ""}
      <div class="setup-legacy-data-checks">
        <label><input type="checkbox" data-setup-legacy="group-import-network" ${legacyGroupImportNetwork ? "checked" : ""} ${network ? "" : "disabled"}><span>导入群成员互动图</span></label>
        <label><input type="checkbox" data-setup-legacy="group-import-worldbook" ${legacyGroupImportWorldbook ? "checked" : ""} ${Number(counts.entries) + Number(counts.members) > 0 ? "" : "disabled"}><span>导入群范围资料</span></label>
      </div>
      ${legacyGroupPlan ? `<label class="setup-legacy-confirm"><input type="checkbox" data-setup-legacy="group-confirm-mapping" ${legacyGroupConfirmMapping ? "checked" : ""}><span>确认 V1 群 ${escape(legacyGroupPlan.source_group_id)} 对应 V2 平台 ${escape(legacyGroupPlan.target?.platform_id || "")}、账号 ${escape(legacyGroupPlan.target?.account_id || "")}、群 ${escape(legacyGroupPlan.target?.group_id || "")}</span></label>
        ${(legacyGroupImportNetwork || legacyGroupImportWorldbook) ? `<label class="setup-legacy-confirm"><input type="checkbox" data-setup-legacy="group-confirm-member-ids" ${legacyGroupConfirmMemberIds ? "checked" : ""}><span>确认所选目标平台中的成员账号 ID 与 V1 历史记录一致</span></label>` : ""}` : ""}
      ${legacyGroupResult ? `<p>最近一次群迁移结果已记录；重复执行将按原有来源标识去重。</p>` : ""}
      <div class="setup-actions">${legacyButton("legacy-group-data-plan", legacyGroupPlan ? "重新试算群映射" : "试算群映射", {primary: !legacyGroupPlan, disabled: !canPlan})}${canApply ? legacyButton("legacy-group-data-apply", "导入所选群数据", {primary: true}) : ""}</div>
    </section>`;
  }

  function legacyScopeStatus(plan = legacyPlan) {
    return Array.isArray(plan?.scope_status) ? plan.scope_status : [];
  }

  function legacyScopePanel() {
    const choices = legacyChoices();
    return `<section class="setup-stage setup-legacy setup-legacy-scope-only">
      <header class="setup-migration-header"><div><p class="setup-kicker">V1 DATA</p><h3>V1 数据迁移</h3><p>选择来源、写入目标和配置范围。</p></div><span class="setup-migration-badge">V1 只读</span></header>
      <div class="setup-migration-context">
        <section class="setup-migration-step"><span class="setup-migration-step-index">01</span><div><h4>迁移来源</h4>
          <label class="setup-legacy-path"><span>V1 数据目录（可选）</span><input type="text" inputmode="text" autocomplete="off" spellcheck="false" data-setup-legacy="root" value="${escape(legacyRootDraft)}" placeholder="留空时自动查找"></label>
          <p class="setup-legacy-scope-note">手动填写时使用 AstrBot 插件数据目录的绝对路径。</p>
        </div></section>
        <section class="setup-migration-step"><span class="setup-migration-step-index">02</span><div><h4>V2 写入目标</h4>
          <div class="setup-legacy-scope">
            <label><span>会话对象</span><select data-setup-legacy="target"><option value="">选择目标</option>${choices.targets.map(item => `<option value="${escape(item.target_id)}" ${legacyTargetId === item.target_id ? "selected" : ""}>${escape(legacyTargetLabel(item))} · ${escape(legacyAccountLabel(item))}</option>`).join("")}</select></label>
            <label><span>人格</span><select data-setup-legacy="role" ${legacyTargetId ? "" : "disabled"}><option value="">选择人格</option>${choices.roles.map((item,index) => `<option value="${escape(item.role_id)}" ${legacyRoleId === item.role_id ? "selected" : ""}>${escape(legacyRoleLabel(item,index))}</option>`).join("")}</select></label>
          </div>
        </div></section>
        <section class="setup-migration-step"><span class="setup-migration-step-index">03</span><div><h4>配置范围</h4>
          <label class="setup-legacy-path"><span>迁移配置</span><select data-setup-legacy="configuration-scope">
            <option value="proactive" ${legacyConfigScope === "proactive" ? "selected" : ""}>主动消息与天气基础设置</option>
            <option value="all" ${legacyConfigScope === "all" ? "selected" : ""}>全部可迁移配置</option>
          </select></label>
        </div></section>
      </div>
      <p class="setup-migration-prompt">选择 V2 目标和人格后，可检查配置并试算资料导入。</p>
    </section>`;
  }

  function legacyButton(action, label, {primary = false, disabled = false} = {}) {
    return `<button type="button" class="button${primary ? " primary" : ""}" data-setup-legacy-action="${escape(action)}" ${disabled || busy ? "disabled" : ""}>${escape(label)}</button>`;
  }

  function legacyPanel() {
    const selection = legacySelection();
    const legacyScope = selection.role;
    if (!legacyScope) return legacyScopePanel();
    const targets = selection.targets;
    const roles = selection.roles;
    const statuses = {ready: "可转换", data_ready: "可导入数据", absent: "未发现", no_handler: "暂缺转换器", read_only: "只读保留",
      external: "由其他插件负责", held: "归属待确认", documented_skip: "按边界跳过", unreadable: "存在但不可读取"};
    const findings = legacyFinding?.findings || legacyPlan?.findings || [];
    const planScopes = legacyScopeStatus();
    const blocked = planScopes.length > 0 && !planScopes.some(item => item.available);
    const plannedSettings = (legacyPlan?.intents || []).flatMap(intent =>
      Object.entries(intent.values || {}).map(([field, value]) => ({
        field: intent.target_kind === "plugin_config" ? field : `${intent.group_id}.${field}`, value,
        confidence: intent.confidence?.[field] || "high",
        sources: intent.sources?.[field] || [],
        pluginConfig: intent.target_kind === "plugin_config",
      })));
    const auditDifferences = (legacyPlan?.differences || []).filter(item => item.audit);
    const reviewDifferences = (legacyPlan?.differences || []).filter(item => !item.audit);
    const auditLabels = {manual_required: "仍待实现", manual_mapping: "需要人工核对",
      implemented_elsewhere: "由其他机制承接", not_migrated: "不自动迁移", not_applicable: "不适用"};
    const auditCounts = auditDifferences.reduce((counts, item) => {
      const label = auditLabels[item.disposition] || "待核对";
      counts[label] = (counts[label] || 0) + 1;
      return counts;
    }, {});
    const auditSummary = Object.entries(auditCounts).map(([label, count]) => `${label} ${count}`).join(" · ");
    const canApply = Boolean(legacyPlan?.plan_token && legacyPlan.change_count > 0
      && planScopes.some(item => item.available));
    const reactionSummary = legacyDataPlan?.reaction_assets || {};
    const journalSummary = legacyDataPlan?.journals || {};
    const worldbookSummary = legacyDataPlan?.worldbook || {};
    const referenceSummary = legacyDataPlan?.reference_images || {};
    const wardrobeSummary = legacyDataPlan?.wardrobe_items || {};
    const profileSummary = legacyDataPlan?.profile_data || {};
    const workSummary = legacyDataPlan?.work_delivery || {};
    const worldSummary = legacyDataPlan?.world_assets || {};
    const memoryDatabase = legacyDataPlan?.memory_database || {};
    const memoryTables = Object.entries(memoryDatabase.table_counts || {});
    const memoryProjection = memoryDatabase.projection || {};
    const memoryInventory = memoryDatabase.identity_inventory || {};
    const memoryOwners = memoryInventory.owners || [];
    const privateMemoryOwners = memoryOwners.filter(item => item.source?.scope === "private");
    const groupMemoryOwners = memoryOwners.filter(item => item.source?.scope === "group");
    const memoryGroupTargets = memoryDatabase.group_targets || [];
    const memoryArchiveOnly = memoryDatabase.archive_only || {};
    const memoryArchiveAvailable = legacyMemoryArchiveCanApply(memoryDatabase);
    const sourceArchiveAvailable = legacyArchiveCanApply(legacyDataPlan?.archive);
    const referencesReady = Boolean(legacyImportReferenceImages
      && Number(referenceSummary.batch_count) > 0 && legacyDataPlan?.target_private_available);
    const wardrobeReady = Boolean(legacyImportWardrobeItems
      && Number(wardrobeSummary.batch_count) > 0 && legacyDataPlan?.target_private_available);
    const networkGroupOptions = legacyDataPlan?.group_networks || [];
    const worldbookGroupOptions = worldbookSummary.groups || [];
    const groupOptionMap = new Map(networkGroupOptions.map(item => [item.source_group_id, {...item,
      worldbook_entry_count: Number(worldbookGroupOptions.find(group => group.source_group_id === item.source_group_id)?.entry_count) || 0}]));
    for (const item of worldbookGroupOptions) {
      if (groupOptionMap.has(item.source_group_id)) continue;
      groupOptionMap.set(item.source_group_id, {source_group_id: item.source_group_id,
        member_count: 0, edge_count: 0, worldbook_entry_count: Number(item.entry_count) || 0});
    }
    const groupOptions = [...groupOptionMap.values()];
    const personaOptions = legacyDataPlan?.persona_sources || [];
    const selectedGroup = groupOptions.find(item => item.source_group_id === legacyDataGroupId) || null;
    const selectedNetworkGroup = networkGroupOptions.find(item => item.source_group_id === legacyDataGroupId) || null;
    const selectedWorldbookGroup = worldbookGroupOptions.find(item => item.source_group_id === legacyDataGroupId) || null;
    const selectedPersona = personaOptions.find(item => item.persona_id === legacyDataPersonaId) || null;
    const worldbookImportableCount = Number(worldbookSummary.available_count) || 0;
    const worldbookCanApply = Boolean(legacyImportWorldbook
      && ((Number(worldbookSummary.general_count) > 0 && !worldbookSummary.base_entries_matches)
        || (legacyConfirmMemberIds && Number(worldbookSummary.member_count) > 0
          && !worldbookSummary.base_members_matches)
        || (legacyConfirmMemberIds && legacyDataPlan?.group_target_available
          && Number(worldbookSummary.selected_group_entry_count) + Number(worldbookSummary.selected_group_member_count || 0) > 0
          && !worldbookSummary.group_matches)));
    const canApplyData = Boolean(legacyDataPlan?.plan_token
      && !legacyMemoryPlanDirty
      && (!(legacyMemoryOwnerIds.size || legacyMemoryGroupMappings.size) || legacyConfirmMemoryMapping)
      && ((legacyImportReactions && Number(reactionSummary.batch_count) > 0)
        || (legacyImportArchive && sourceArchiveAvailable)
        || (legacyImportMemoryDatabase && memoryArchiveAvailable
          && (!legacyMemoryOwnerIds.size || legacyDataPlan.target_private_available)
          )
        || (legacyImportGroupNetwork && selectedNetworkGroup && legacyDataPlan.group_target_available
          && legacyConfirmMemberIds)
        || (legacyImportJournals && Number(journalSummary.batch_count) > 0
          && legacyDataPlan.target_private_available && legacyConfirmPersonaMapping)
        || ((referencesReady || wardrobeReady) && legacyConfirmReferencePersonaMapping)
        || worldbookCanApply));
    const dataReasons = {target_image_limit: "超过 V2 单张图片限制", unsupported_image_type: "V2 不支持此图片格式",
      invalid_filename: "文件名不安全", image_missing: "素材文件缺失", image_path_outside_library: "文件位于素材目录之外",
      catalog_hash_mismatch: "目录哈希与文件不一致", asset_count_limit: "超过单次扫描条数",
      remote_url_not_downloaded: "远程图片 URL 不会在迁移时下载",
      identity_scope_unmapped: "素材绑定了具体用户或群，无法映射为角色级授权",
      image_access_not_role_wide: "素材授权范围不是角色级公开授权",
      reference_disabled: "V1 中已停用的参考图不恢复", image_changed_after_preview: "试算后源图发生变化，请重新试算",
      entry_invalid: "世界书条目格式无法识别", entry_content_missing: "条目没有可导入正文",
      entry_too_large: "条目正文超过单条限制", member_scope_missing: "成员条目没有账号范围",
      member_scope_unmapped: "成员账号范围无法确认", group_scope_missing: "群条目没有群范围",
      group_scope_invalid: "群范围无法识别", unsupported_scoped_template: "此模板的范围语义未映射",
      worldbook_batch_bytes_limit: "超过世界书单批容量", worldbook_count_limit: "超过单次扫描条数",
      member_profile_preferred_or_deleted: "使用成员档案中的最新关系资料；已删除的节点保持删除"};
    return `<section class="setup-stage setup-legacy">
      <header class="setup-migration-header"><div><p class="setup-kicker">V1 DATA</p><h3>V1 数据迁移</h3><p>先检查与试算，再确认写入。</p></div><span class="setup-migration-badge">V1 只读</span></header>
      <div class="setup-migration-context">
        <section class="setup-migration-step"><span class="setup-migration-step-index">01</span><div><h4>迁移来源</h4>
          <label class="setup-legacy-path"><span>V1 数据目录（可选）</span><input type="text" inputmode="text" autocomplete="off" spellcheck="false" data-setup-legacy="root" value="${escape(legacyRootDraft)}" placeholder="留空时自动查找"></label>
          <p class="setup-legacy-scope-note">手动填写时使用 AstrBot 插件数据目录的绝对路径。</p>
        </div></section>
        <section class="setup-migration-step"><span class="setup-migration-step-index">02</span><div><h4>V2 写入目标</h4>
          <div class="setup-legacy-scope">
            <label><span>会话对象</span><select data-setup-legacy="target"><option value="">选择目标</option>${targets.map(item => `<option value="${escape(item.target_id)}" ${legacyTargetId === item.target_id ? "selected" : ""}>${escape(legacyTargetLabel(item))} · ${escape(legacyAccountLabel(item))}</option>`).join("")}</select></label>
            <label><span>人格</span><select data-setup-legacy="role" ${legacyTargetId ? "" : "disabled"}><option value="">选择人格</option>${roles.map((item,index) => `<option value="${escape(item.role_id)}" ${legacyRoleId === item.role_id ? "selected" : ""}>${escape(legacyRoleLabel(item,index))}</option>`).join("")}</select></label>
          </div>
        </div></section>
        <section class="setup-migration-step"><span class="setup-migration-step-index">03</span><div><h4>配置范围</h4>
          <label class="setup-legacy-path"><span>迁移配置</span><select data-setup-legacy="configuration-scope">
            <option value="proactive" ${legacyConfigScope === "proactive" ? "selected" : ""}>主动消息与天气基础设置</option>
            <option value="all" ${legacyConfigScope === "all" ? "selected" : ""}>全部可迁移配置</option>
          </select></label>
          <p class="setup-legacy-scope-note">V2 已有明确设置会保留。</p>
        </div></section>
      </div>
      <div class="setup-migration-review">
      ${legacyError ? `<p class="setup-inline-error">${escape(legacyError)}</p>` : ""}
      ${legacyResult ? `<p class="setup-recorded">${legacyConfigScope === "proactive" ? "主动消息配置" : "迁移配置"}已写入 ${Number(legacyResult.written_count) || 0} 项 V2 设置。V1 文件保持不变。${legacyResult.restart_required ? "请重启插件使插件级配置生效。" : ""}</p>` : ""}
      ${legacyFinding || legacyPlan ? `<p class="setup-legacy-root">V1 位置：${escape(legacyFinding?.v1_root || legacyPlan?.v1_root || "")}</p>
        <ul class="setup-legacy-findings">${findings.map(item => `<li><strong>${escape(legacySources[item.source_id] || "其他旧版资料")}</strong><span>${escape(statuses[item.state] || "状态待核对")}</span><small>${escape(item.detail || "")}</small></li>`).join("")}</ul>` : ""}
      ${legacyPlan ? `<div class="setup-legacy-plan"><p>本次${legacyConfigScope === "proactive" ? "主动消息与天气基础设置" : "全部可迁移配置"}试算将写入 ${Number(legacyPlan.change_count) || 0} 项。</p>
        ${(legacyPlan.warnings || []).map(item => `<p>${escape(item)}</p>`).join("")}
        ${reviewDifferences.map(item => `<p>${escape(item.field)}${item.before !== undefined || item.after !== undefined ? `：${escape(item.before ?? "")} → ${escape(item.after ?? "")}` : ""}。${escape(item.explain || item.summary || "")}</p>`).join("")}
        ${auditDifferences.length ? `<details class="setup-legacy-values setup-legacy-audit"><summary>配置未自动迁移（${auditDifferences.length}）${auditSummary ? ` · ${escape(auditSummary)}` : ""}</summary><ul>${auditDifferences.map(item => `<li><strong>${escape(item.source_key || item.field || "未命名配置")}</strong><small>${escape(auditLabels[item.disposition] || "待核对")}</small><span>${escape(item.explain || item.summary || "没有经过核实的自动转换规则。")}</span></li>`).join("")}</ul></details>` : ""}
        ${plannedSettings.length ? `<details class="setup-legacy-values"><summary>拟写入字段与数值（${plannedSettings.length}）</summary><ul>${plannedSettings.map(item => `<li><strong>${escape(item.field)}</strong><code>${escape(typeof item.value === "string" ? item.value : JSON.stringify(item.value))}</code><small>${item.confidence === "medium" ? "中置信映射" : "高置信映射"}${item.pluginConfig ? " · 插件设置需重启生效" : ""}${item.sources.length ? ` · ${escape(item.sources.join("、"))}` : ""}</small></li>`).join("")}</ul></details>` : ""}
        ${blocked ? `<p class="setup-inline-error">有作用域暂不可写：${escape(planScopes.filter(item => !item.available).map(item => item.scope).join("、"))}</p>` : ""}
      </div>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">
        ${legacyButton("legacy-scan", legacyFinding ? "重新检查 V1" : "检查 V1 配置",
          {primary: true, disabled: !selection.api})}
        ${legacyFinding && !legacyPlan ? legacyButton("legacy-plan", "试算迁移") : ""}
        ${legacyPlan && !legacyResult && legacyPlan.change_count > 0 ? legacyButton("legacy-apply", "写入 V2", {primary: true, disabled: !canApply}) : ""}
      </div>
      </div>
      <div class="setup-legacy-data">
        <header class="setup-migration-section-head"><span>04</span><div><h4>资料范围与映射</h4><p>先试算生成清单；群资料需另选 V2 群目标，个人关系账户不在此处迁移。</p></div></header>
        ${legacyDataErrorMarkup()}
        ${legacyDataResult ? `<p class="setup-recorded">已导入表情 ${Number(legacyDataResult.reaction_created) || 0} 张，重复 ${Number(legacyDataResult.reaction_duplicates) || 0} 张；尚有 ${Number(legacyDataResult.reaction_remaining) || 0} 张待分批处理。日记与梦境导入 ${Number(legacyDataResult.journal_created) || 0} 条，尚有 ${Number(legacyDataResult.journal_remaining) || 0} 条待分批处理。${legacyDataResult.reference_images ? `参考图库新增 ${Number(legacyDataResult.reference_images.reference_created) || 0} 张，衣柜新增 ${Number(legacyDataResult.reference_images.wardrobe_created) || 0} 件；待继续 ${Number(legacyDataResult.reference_images.reference_remaining) || 0} 张参考图、${Number(legacyDataResult.reference_images.wardrobe_remaining) || 0} 件衣物${Number(legacyDataResult.reference_images.wardrobe_images_skipped) ? `，${Number(legacyDataResult.reference_images.wardrobe_images_skipped)} 件衣物保留文字但未关联图片` : ""}。` : ""}${legacyDataResult.group_network ? `群成员互动图新增 ${Number(legacyDataResult.group_network.members_added) || 0} 位成员、${Number(legacyDataResult.group_network.edges_added) || 0} 条互动边${legacyDataResult.group_network.duplicate ? "（此前已导入）" : ""}。` : ""}${legacyDataResult.memory_archive ? `独立记忆库快照保留 ${Number(legacyDataResult.memory_archive.record_count) || 0} 条记录 / ${Number(legacyDataResult.memory_archive.file_count) || 0} 个文件${legacyDataResult.memory_archive.source_complete === false ? `（部分归档，${Number(legacyDataResult.memory_archive.source_issues?.length) || 0} 项未纳入）` : ""}${legacyDataResult.memory_archive.already_present ? "（已存在，未重复归档）" : ""}。` : ""}${legacyDataResult.memory_materials ? `V2 私聊历史已导入 ${Number(legacyDataResult.memory_materials.imported?.memories) || 0} 条记忆、${Number(legacyDataResult.memory_materials.imported?.timeline) || 0} 条时间线${legacyDataResult.memory_materials.already_present ? "（已存在，未重复导入）" : legacyDataResult.memory_materials.state === "archive_only" ? "（仅归档，未选择身份映射）" : ""}。` : ""}${legacyDataResult.archive ? `原始资料归档 ${Number(legacyDataResult.archive.file_count) || 0} 个文件 / ${Math.ceil((Number(legacyDataResult.archive.total_bytes) || 0) / 1048576)} MB${legacyDataResult.archive.complete === false ? `（归档不完整，排除 ${Number(legacyDataResult.archive.excluded_count) || 0} 项）` : ""}${legacyDataResult.archive.already_present ? "（已存在，未重复复制）" : ""}。` : ""}${legacyDataResult.errors?.length ? `另有 ${legacyDataResult.errors.length} 项未能导入，原因已记录。` : ""}</p>` : ""}
        ${legacyDataResult?.worldbook ? `<p class="setup-recorded">世界书：普通条目 ${Number(legacyDataResult.worldbook.entries_imported) || 0} 条，学习关系网节点 ${Number(legacyDataResult.worldbook.members_imported) || 0} 个，群范围条目 ${Number(legacyDataResult.worldbook.group_entries_imported) || 0} 条。${Number(legacyDataResult.worldbook.member_ids_unconfirmed) ? `有 ${Number(legacyDataResult.worldbook.member_ids_unconfirmed)} 条成员范围内容未导入，因为未确认账号映射。` : ""}${Number(legacyDataResult.worldbook.group_entries_unmapped) ? `另有 ${Number(legacyDataResult.worldbook.group_entries_unmapped)} 条其他群范围内容需选择对应群后单独导入。` : ""}</p>` : ""}
        ${legacyDataPlan ? `<div class="setup-legacy-plan">
          <p>表情素材：${Number(reactionSummary.ready) || 0} 张待导入，已存在 ${Number(reactionSummary.already_present) || 0} 张；本批 ${Number(reactionSummary.batch_count) || 0} 张 / ${Math.ceil((Number(reactionSummary.batch_bytes) || 0) / 1048576)} MB${Number(reactionSummary.remaining_after_batch) ? `，后续还需 ${Number(reactionSummary.remaining_after_batch)} 张` : ""}。</p>
          <p>日记与梦境：${Number(journalSummary.ready) || 0} 条待导入，${Number(journalSummary.already_present) || 0} 个日期已有 V2 记录会保留；本批 ${Number(journalSummary.batch_count) || 0} 条 / ${Math.ceil((Number(journalSummary.batch_bytes) || 0) / 1024)} KB${Number(journalSummary.remaining_after_batch) ? `，后续还需 ${Number(journalSummary.remaining_after_batch)} 条` : ""}。预览只显示日期和大小，不显示正文。</p>
          ${journalSummary.samples?.length ? `<p>本批日期：${journalSummary.samples.slice(0, 12).map(item => `${escape(item.date)}（${escape(item.kind === "dream" ? "梦境" : "日记")}，${Number(item.size) || 0} 字节）`).join("、")}</p>` : ""}
          ${journalSummary.conflicts?.length ? `<p>已有日期：${journalSummary.conflicts.slice(0, 12).map(item => `${escape(item.date)}（${escape(item.kind === "dream" ? "梦境" : "日记")}，${item.imported ? "此前由迁移导入" : `V2 已有 ${escape(item.state)} 记录，保留不覆盖`}）`).join("、")}</p>` : ""}
          <p>世界书条目：${Number(worldbookSummary.general_count) || 0} 条普通条目、${Number(worldbookSummary.member_count) || 0} 个学习关系网节点、${Number(worldbookSummary.group_count) || 0} 条群范围条目；当前目标可导入 ${worldbookImportableCount} 条。${Number(worldbookSummary.disabled_member_count) ? `另有 ${Number(worldbookSummary.disabled_member_count)} 条已禁用成员条目，V2 无法保留其禁用状态，已跳过。` : ""}人物描述、身份备注、相处边界与重要印象一起迁移。同一账号合并为一个节点；群范围按所选 V1 群单独映射，预览不显示正文。</p>
          <p>参考图库：${Number(referenceSummary.ready) || 0} 张可导入，${Number(referenceSummary.already_present) || 0} 张已存在；本批 ${Number(referenceSummary.batch_count) || 0} 张。衣柜：${Number(wardrobeSummary.ready) || 0} 件可导入，图片 ${Number(wardrobeSummary.image_count) || 0} 张；本批 ${Number(wardrobeSummary.batch_count) || 0} 件。源文件会复核 SHA-256；URL 不下载，无法安全映射的素材会跳过。</p>
          ${(referenceSummary.rejected?.length || wardrobeSummary.rejected?.length) ? `<details class="setup-legacy-values"><summary>参考图与衣柜跳过项（${(referenceSummary.rejected?.length || 0) + (wardrobeSummary.rejected?.length || 0)}）</summary><ul>${[...(referenceSummary.rejected || []), ...(wardrobeSummary.rejected || [])].map(item => `<li><strong>${escape(item.filename || item.source_id || "衣柜条目")}</strong><small>${escape(dataReasons[item.reason] || item.reason || "无法迁移")}</small></li>`).join("")}</ul></details>` : ""}
          <p>未直接转换为 V2 运行语义的旧档案：${Number(profileSummary.private_user_profiles) || 0} 个私人画像、${Number(profileSummary.dream_fragments) || 0} 个梦境碎片。原始资料可完整保存在下方的隔离归档中。</p>
          <p>旧任务 / 投递：${escape(workSummary.work?.state || "未发现")}，${Object.values(workSummary.work?.tables || {}).reduce((sum, value) => sum + (Number(value) || 0), 0)} 条任务库记录；${escape(workSummary.delivery?.state || "未发现")}，${Object.values(workSummary.delivery?.tables || {}).reduce((sum, value) => sum + (Number(value) || 0), 0)} 条投递库记录。${escape(workSummary.reason || "")}</p>
          <p>旧相册：${escape(worldSummary.album?.state || "未发现")}，本地资源 ${Number(worldSummary.resource_files) || 0} 个、图片约 ${Math.ceil((Number(worldSummary.image_bytes) || 0) / 1048576)} MB。${escape(worldSummary.reason || "")}</p>
          <p>其余原始文件：${Number(legacyDataPlan.archive?.file_count) || 0} 个，约 ${Math.ceil((Number(legacyDataPlan.archive?.total_bytes) || 0) / 1048576)} MB；${Number(legacyDataPlan.archive?.excluded_count) ? `${Number(legacyDataPlan.archive.excluded_count)} 个链接或不可读项目无法安全归档；其余可读文件可以归档，清单会标记不完整。` : "全部普通文件可归档。"}归档按文件校验 SHA-256，不会提供给对话或执行旧任务。</p>
          <p>独立记忆库：${escape(memoryDatabase.state || "未试算")}，原始快照 ${Number(memoryDatabase.table_count) || 0} 张表 / ${Number(memoryDatabase.record_count) || 0} 条记录，约 ${Math.ceil((Number(memoryDatabase.total_bytes) || 0) / 1048576)} MB。已映射预览可查询 ${Number(memoryProjection.imported?.memories) || 0} 条记忆、${Number(memoryProjection.imported?.timeline) || 0} 条时间线；未通过映射或治理检查的内容继续只保留在隔离归档中，不会写入 V2 活跃事实或任务。</p>
          <p>归档专属：未迁入 ${Number(memoryArchiveOnly.group_owner_count) || 0} 个身份 / ${Number(memoryArchiveOnly.group_record_count) || 0} 条群记录；哈希命名空间 ${Number(memoryArchiveOnly.hashed_namespace_record_count) || 0} 条；身份缺失 ${Number(memoryArchiveOnly.unresolved_records) || 0} 条；未映射私聊 ${Number(memoryArchiveOnly.unmapped_private_records) || 0} 条。${Number(memoryDatabase.excluded_count) ? `另有 ${Number(memoryDatabase.excluded_count)} 个资产无法安全读取。` : ""}</p>
          ${memoryTables.length ? `<details class="setup-legacy-values"><summary>独立记忆库表清单（${memoryTables.length}）</summary><ul>${memoryTables.map(([name, count]) => `<li><strong>${escape(name)}</strong><small>${Number(count) || 0} 条</small></li>`).join("")}</ul></details>` : ""}
          ${reactionSummary.rejected?.length ? `<details class="setup-legacy-values"><summary>已跳过素材（${reactionSummary.rejected.length}）</summary><ul>${reactionSummary.rejected.slice(0, 30).map(item => `<li><strong>${escape(item.filename || "未命名素材")}</strong><small>${escape(dataReasons[item.reason] || item.reason || "无法读取")}</small></li>`).join("")}</ul></details>` : ""}
          ${journalSummary.rejected?.length ? `<details class="setup-legacy-values"><summary>未导入的日记或梦境（${journalSummary.rejected.length}）</summary><ul>${journalSummary.rejected.slice(0, 30).map(item => `<li><strong>${escape(item.date || item.kind || "记录")}</strong><small>${escape(item.reason || "记录格式无法识别")}</small></li>`).join("")}</ul></details>` : ""}
          ${worldbookSummary.rejected?.length ? `<details class="setup-legacy-values"><summary>未映射的世界书条目（${worldbookSummary.rejected.length}）</summary><ul>${worldbookSummary.rejected.slice(0, 30).map(item => `<li><strong>条目 ${Number(item.index) + 1}</strong><small>${escape(dataReasons[item.reason] || item.reason || "条目格式无法识别")}</small></li>`).join("")}</ul></details>` : ""}
          ${legacyDataPlan.warnings?.map(item => `<p>${escape(item)}</p>`).join("") || ""}
        </div>` : ""}
        <div class="setup-legacy-data-controls">
          <label class="setup-legacy-path"><span>V1 人格档案</span><select data-setup-legacy="data-persona" ${personaOptions.length ? "" : "disabled"}><option value="">主角色（companions.json）</option>${personaOptions.filter(item => item.persona_id).map(item => `<option value="${escape(item.persona_id)}" ${legacyDataPersonaId === item.persona_id ? "selected" : ""} ${item.state === "ready" ? "" : "disabled"}>${escape(item.label)}${item.state === "ready" ? "" : " · 不可读取"}</option>`).join("")}</select></label>
          ${selectedPersona ? `<p class="setup-legacy-scope-note">日记、梦境和群成员互动图来自 ${escape(selectedPersona.label)}；不同 V1 人格不会混在一起。</p>` : ""}
          <label class="setup-legacy-path"><span>V1 群记录 / 范围</span><select data-setup-legacy="data-group" ${groupOptions.length ? "" : "disabled"}><option value="">不选择群</option>${groupOptions.map(item => `<option value="${escape(item.source_group_id)}" ${legacyDataGroupId === item.source_group_id ? "selected" : ""}>群 ${escape(item.source_group_id)} · ${Number(item.member_count) || 0} 位成员 / ${Number(item.edge_count) || 0} 条边 / ${Number(item.worldbook_entry_count) || 0} 条知识条目</option>`).join("")}</select></label>
          ${selectedGroup ? `<p class="setup-legacy-scope-note">${selectedNetworkGroup ? `群成员互动图将从 V1 群 ${escape(selectedGroup.source_group_id)} 映射到当前 V2 群 ${escape(legacyDataPlan.target_group_id || "（当前目标不是群）")}，含 ${Number(selectedGroup.member_count) || 0} 位成员和 ${Number(selectedGroup.edge_count) || 0} 条互动边。${Number(selectedGroup.omitted_member_count) || Number(selectedGroup.omitted_edge_count) ? `另有 ${Number(selectedGroup.omitted_member_count) || 0} 位成员、${Number(selectedGroup.omitted_edge_count) || 0} 条互动边超过 V2 上限，不会导入。` : ""}${Number(selectedGroup.rejected_member_count) || Number(selectedGroup.rejected_edge_count) ? `无法识别 ${Number(selectedGroup.rejected_member_count) || 0} 位成员、${Number(selectedGroup.rejected_edge_count) || 0} 条互动边。` : ""}` : ""}${selectedWorldbookGroup ? `所选 V1 群还有 ${Number(selectedWorldbookGroup.entry_count) || 0} 条群范围知识条目。` : ""}</p>` : ""}
        </div>
        <div class="setup-legacy-data-checks">
          <label><input type="checkbox" data-setup-legacy="import-reactions" ${legacyImportReactions ? "checked" : ""}><span>导入表情素材</span></label>
          <label><input type="checkbox" data-setup-legacy="import-group-network" ${legacyImportGroupNetwork ? "checked" : ""} ${selectedNetworkGroup && legacyDataPlan?.group_target_available ? "" : "disabled"}><span>导入所选群成员互动图</span></label>
          <label><input type="checkbox" data-setup-legacy="import-worldbook" ${legacyImportWorldbook ? "checked" : ""} ${worldbookImportableCount ? "" : "disabled"}><span>导入世界书条目</span></label>
          <label><input type="checkbox" data-setup-legacy="import-journals" ${legacyImportJournals ? "checked" : ""} ${legacyDataPlan?.target_private_available ? "" : "disabled"}><span>导入该人格的日记与梦境</span></label>
          <label><input type="checkbox" data-setup-legacy="import-reference-images" ${legacyImportReferenceImages ? "checked" : ""} ${Number(referenceSummary.batch_count) > 0 && legacyDataPlan?.target_private_available ? "" : "disabled"}><span>导入参考图库 ${Number(referenceSummary.batch_count) || 0} 张</span></label>
          <label><input type="checkbox" data-setup-legacy="import-wardrobe-items" ${legacyImportWardrobeItems ? "checked" : ""} ${Number(wardrobeSummary.batch_count) > 0 && legacyDataPlan?.target_private_available ? "" : "disabled"}><span>导入衣柜 ${Number(wardrobeSummary.batch_count) || 0} 件（图片 ${Number(wardrobeSummary.image_count) || 0} 张）</span></label>
          <label><input type="checkbox" data-setup-legacy="import-memory-database" ${legacyImportMemoryDatabase ? "checked" : ""} ${memoryArchiveAvailable ? "" : "disabled"}><span>归档独立记忆库并迁入已映射的历史资料（${legacyDataPlan ? `${Number(memoryDatabase.record_count) || 0} 条 / ${Math.ceil((Number(memoryDatabase.total_bytes) || 0) / 1048576)} MB` : "试算后显示规模"}）</span></label>
          <label><input type="checkbox" data-setup-legacy="import-archive" ${legacyImportArchive ? "checked" : ""} ${sourceArchiveAvailable ? "" : "disabled"}><span>${legacyDataPlan?.archive?.state === "incomplete" ? "尽可能归档可读的原始资料" : "完整保留其余原始资料"}（${Math.ceil((Number(legacyDataPlan?.archive?.total_bytes) || 0) / 1048576)} MB）</span></label>
        </div>
        ${privateMemoryOwners.length ? `<details class="setup-legacy-values"><summary>旧私聊身份映射（${legacyMemoryOwnerIds.size} / ${privateMemoryOwners.length}）</summary><p>仅迁入已映射的合规私聊历史；其余保留在隔离归档。</p><ul>${privateMemoryOwners.map(item => {
          const source = item.source || {};
          const label = `${source.platform || "未知平台"} · ${source.bot_id || "未知机器人"} · ${source.persona_id || "未知人格"} · ${source.session_id || "未知会话"} · ${source.actor_id || "未知用户"}`;
          const selected = legacyMemoryOwnerIds.has(item.owner_id);
          const atLimit = !selected && legacyMemoryOwnerIds.size >= MAX_LEGACY_MEMORY_OWNER_SELECTION;
          return `<li><label><input type="checkbox" data-setup-legacy="memory-owner" data-owner-id="${escape(item.owner_id)}" ${selected ? "checked" : ""} ${legacyDataPlan?.target_private_available && legacyImportMemoryDatabase && !atLimit ? "" : "disabled"}><strong>${escape(label)}</strong><small>${Number(item.memories) || 0} 条记忆 / ${Number(item.timeline) || 0} 条时间线</small></label></li>`;
        }).join("")}</ul></details>` : ""}
        ${groupMemoryOwners.length ? `<details class="setup-legacy-values"><summary>旧群身份映射（${legacyMemoryGroupMappings.size} / ${groupMemoryOwners.length}）</summary><p>群号需与目标一致；平台和角色按目标隔离，导入不会新增读取权限。</p><ul>${groupMemoryOwners.map(item => {
          const source = item.source || {};
          const label = `${source.platform || "未知平台"} · ${source.bot_id || "未知机器人"} · ${source.persona_id || "未知人格"} · 群 ${source.group_id || "未知群号"}`;
          const selected = legacyMemoryGroupMappings.get(item.owner_id) || null;
          const targets = memoryGroupTargets.filter(target => target.group_id === source.group_id);
          const options = targets.flatMap(target => target.roles.map(role => ({
            target_id: target.target_id, role_id: role.role_id,
            label: `${target.platform_id} · ${target.account_id} · ${target.bot_id} · ${role.role_name || role.role_id}`,
          })));
          return `<li><label><strong>${escape(label)}</strong><select data-setup-legacy="memory-group-target" data-owner-id="${escape(item.owner_id)}" ${legacyImportMemoryDatabase && options.length ? "" : "disabled"}><option value="">保留在隔离归档</option>${options.map(option => {
            const value = JSON.stringify({target_id: option.target_id, role_id: option.role_id});
            const selectedValue = selected ? JSON.stringify(selected) : "";
            return `<option value="${escape(value)}" ${value === selectedValue ? "selected" : ""}>${escape(option.label)}</option>`;
          }).join("")}</select><small>${Number(item.memories) || 0} 条记忆 / ${Number(item.timeline) || 0} 条时间线</small></label></li>`;
        }).join("")}</ul></details>` : ""}
        ${legacyMemoryOwnerIds.size || legacyMemoryGroupMappings.size ? `<label class="setup-legacy-confirm"><input type="checkbox" data-setup-legacy="confirm-memory-mapping" ${legacyConfirmMemoryMapping ? "checked" : ""} ${legacyImportMemoryDatabase ? "" : "disabled"}><span>确认所选旧私聊与群身份属于对应 V2 目标；群历史只映射到同号群，不新增或扩大读取权限</span></label>` : ""}
        ${legacyDataPlan && legacyMemoryPlanDirty ? `<p class="setup-legacy-scope-note">身份选择已更改；请重新试算后再执行导入。</p>` : ""}
        ${(legacyImportGroupNetwork && selectedNetworkGroup || legacyImportWorldbook && worldbookSummary.requires_id_confirmation) ? `<label class="setup-legacy-confirm"><input type="checkbox" data-setup-legacy="confirm-member-ids" ${legacyConfirmMemberIds ? "checked" : ""}><span>确认 V1 与当前 V2 目标使用相同的平台身份，成员账号 ID 一致；所选群范围映射到当前 V2 群</span></label>` : ""}
        ${legacyImportJournals && legacyDataPlan?.target_private_available ? `<label class="setup-legacy-confirm"><input type="checkbox" data-setup-legacy="confirm-persona-mapping" ${legacyConfirmPersonaMapping ? "checked" : ""}><span>确认将 ${escape(selectedPersona?.label || "主角色（companions.json）")} 的私人日记与梦境归入当前 V2 目标和人格</span></label>` : ""}
        ${(referencesReady || wardrobeReady) ? `<label class="setup-legacy-confirm"><input type="checkbox" data-setup-legacy="confirm-reference-persona-mapping" ${legacyConfirmReferencePersonaMapping ? "checked" : ""}><span>确认将 ${escape(selectedPersona?.label || "主角色（companions.json）")} 的参考图与衣柜归入当前 V2 私聊角色；图片不可用时仍保留衣物文字资料</span></label>` : ""}
        ${legacyDataPlan && !legacyDataPlan.group_target_available && selectedGroup ? `<p class="setup-legacy-scope-note">当前 V2 目标不是群会话；切换到对应群目标后才能导入群成员互动图。</p>` : ""}
        ${legacyDataPlan && !legacyDataPlan.target_private_available ? `<p class="setup-legacy-scope-note">日记与梦境只能导入到私聊目标，请切换到当前角色的 V2 私聊目标。</p>` : ""}
        <div class="setup-actions">
          ${legacyButton("legacy-data-plan", legacyDataPlan ? "重新试算数据" : "试算 V1 人物资料", {primary: !legacyDataPlan, disabled: !selection.api})}
          ${legacyDataPlan && canApplyData ? legacyButton("legacy-data-apply", legacyDataResult ? "继续导入下一批" : "导入所选数据", {primary: true}) : ""}
        </div>
      </div>
      ${legacyDataPlan ? renderLegacyPersonaBatch(personaOptions) : ""}
      ${legacyDataPlan && legacyDataGroupId ? renderLegacyGroupMapping() : ""}
    </section>`;
  }

  function legacyDataErrorMarkup() {
    return legacyDataError ? `<p class="setup-inline-error">${escape(legacyDataError)}</p>` : "";
  }

  function bindingFacts(binding) {
    if (!binding || !binding.participant_id) return "";
    return `<dl class="setup-facts">
      <div><dt>平台</dt><dd>${escape(product()?.platformLabel?.(binding) || "QQ · OneBot")}</dd></div>
      <div><dt>Bot 账号</dt><dd>${escape(legacyAccountLabel(binding))}</dd></div>
      <div><dt>私聊对象</dt><dd>${escape(legacyTargetLabel(binding))}</dd></div>
      <div><dt>AstrBot 人格</dt><dd>${escape(binding.persona_id === "[%None]" ? "默认人格" : binding.persona_id || "跟随当前会话")}</dd></div>
    </dl>`;
  }

  function renderBinding() {
    const binding = state?.binding || {};
    const command = "companion_bind";
    if (binding.pending) {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 1</p><h3>核对核心管理员窗口</h3>
        <p>已收到这条私聊里的绑定指令。核对它是你希望 V2 接收管理员指令、也作为主动消息主要投递窗口的私聊。</p>
        <p class="setup-command"><code>${escape(command)}</code></p>
        ${connectionDiagnostic()}
        ${bindingFacts(binding)}
        <p class="setup-confirm-copy">候选绑定仅保存在 V2 数据根，不会触发聊天回复。平台、Bot 账号、私聊对象和人格均正确后，点击确认。</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("confirm-binding", "确认此窗口", {primary: true})}${button("refresh", "重新读取")}</div>
      </section>`;
    }
    if (state?.binding_confirmed) {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 1</p><h3>核心管理员窗口已绑定</h3>
        ${bindingFacts(binding)}
        <p>这个私聊窗口用于管理员控制，也是主动消息测试的目标。下一步配置模型后，V2 才会建立运行实例。</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("refresh", "继续配置模型", {primary: true})}</div>
      </section>`;
    }
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 1</p><h3>绑定核心管理员窗口</h3>
      <p>在希望 V2 接收管理员指令、也作为主动消息主要投递窗口的私聊中，发送固定指令：</p>
      <p class="setup-command"><code>${escape(command)}</code></p>
      <p>回到这里核对平台、Bot 账号、私聊对象和人格，再由 Dashboard 管理员确认。若该账号使用多个人格，可发送 <code>companion_bind 人格名</code> 指定。</p>
      ${connectionDiagnostic()}
      ${state?.settings_error ? `<p class="setup-inline-error">${escape(product()?.errorLabel?.(state.settings_error) || "运行设置尚未就绪，请核对账号、人格与模型。")}</p>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">${button("refresh", "我已发送，检查绑定", {primary: true})}</div>
    </section>`;
  }

  function renderSection(step) {
    const definitions = {
      knowledge: {number: "STEP 4", title: "从人格整理角色设定", target: "role_profile", canSkip: true},
      relationships: {number: "STEP 5", title: "整理熟人卡", target: "relationship_profile", canSkip: true},
    }[step];
    const complete = state?.completed?.includes(step);
    const skipped = state?.skipped?.includes(step);
    const target = definitions.target;
    const current = profileState?.[target];
    const draft = profileDraftTarget === target ? profileDraft : null;
    const fields = draft?.fields || {};
    const currentValues = current?.settings || {};
    const draftFields = Object.keys(fields).filter(name => profileSelected.has(name)
      || String(profileFieldDrafts[name] ?? fields[name] ?? "").trim());
    const fieldMarkup = draftFields.map(name => {
      const value = profileFieldDrafts[name] ?? fields[name] ?? "";
      const limit = Number(draft?.limits?.[name] || 0);
      const exists = Boolean(String(currentValues[name] || "").trim());
      return `<label class="setup-profile-field"><span><input type="checkbox" data-profile-select="${escape(name)}" ${profileSelected.has(name) ? "checked" : ""} ${busy ? "disabled" : ""}><strong>${escape(PROFILE_LABELS[name] || name)}</strong>${exists ? `<small>已有内容</small>` : ""}</span><textarea data-profile-field="${escape(name)}" rows="${value.length > 180 ? 5 : 3}" maxlength="${limit || 6000}" ${busy ? "disabled" : ""}>${escape(value)}</textarea><small class="setup-profile-count">${value.length}${limit ? ` / ${limit}` : ""}</small></label>`;
    }).join("");
    return `<section class="setup-stage">
      <p class="setup-kicker">${definitions.number}</p><h3>${definitions.title}</h3>
      <p>${target === "role_profile" ? "读取当前 AstrBot 人格，结合已导入的 V2 世界资料生成角色档案草稿。检查后直接保存为 V2 角色设定。" : "从当前人格整理对管理员的称呼、关系和相处方式；仅保存到当前私聊的熟人卡。"}</p>
      <label class="setup-profile-supplement"><span>${target === "role_profile" ? "补充已确认的角色事实" : "补充已确认的关系资料"}</span><textarea data-profile-supplement rows="3" maxlength="4000" ${busy ? "disabled" : ""} placeholder="${target === "role_profile" ? "例如：她是人造人，生日是第一次醒来的那天；表达担心时会比较含蓄。" : "例如：希望称呼我为小舟；我是角色的搭档，我们会直接提醒彼此休息。"}">${escape(profileSupplement[target] || "")}</textarea></label>
      ${current ? `<p class="setup-profile-source">当前角色：${escape(state?.binding?.persona_id === "[%None]" ? "默认人格" : state?.binding?.persona_id || "已绑定人格")} · 已保存 ${Object.values(currentValues).filter(value => String(value || "").trim()).length} 项</p>` : ""}
      ${profileNotes.length ? `<ul class="setup-profile-notes">${profileNotes.map(note => `<li>${escape(note)}</li>`).join("")}</ul>` : ""}
      ${draft ? `<section class="setup-profile-preview" aria-label="生成的资料草稿"><header><strong>${target === "role_profile" ? "角色档案草稿" : "熟人卡草稿"}</strong><span>${escape(draft.source?.name || "当前人格")}</span></header>${draft.source?.source_preview ? `<p>${escape(draft.source.source_preview)}</p>` : ""}${target === "role_profile" && draft.knowledge?.length ? `<details><summary>本次参考的世界资料 · ${draft.knowledge.length}</summary><ul>${draft.knowledge.map(item => `<li><strong>${escape(item.title)}</strong><span>${escape(item.source)}</span></li>`).join("")}</ul></details>` : ""}<div class="setup-profile-fields">${fieldMarkup || `<p>没有生成可审阅内容，请补充事实后重新生成。</p>`}</div><label class="setup-overwrite"><input type="checkbox" data-profile-overwrite ${profileOverwrite ? "checked" : ""} ${busy ? "disabled" : ""}><span>覆盖已有字段</span></label><div class="setup-actions">${button("save-profile", target === "role_profile" ? "保存所选角色设定" : "保存所选熟人卡", {primary: true, disabled: !draftFields.length || !current})}${button("generate-profile", "重新生成草稿")}</div></section>` : ""}
      ${!current && !notice ? `<p class="setup-loading">正在读取当前角色设定…</p>` : ""}
      ${complete || skipped ? `<p class="setup-recorded">${skipped ? "已选择暂时跳过" : "已标记完成"}</p>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">
        ${button("generate-profile", draft ? "重新生成人格草稿" : target === "role_profile" ? "从人格生成角色设定" : "从人格生成熟人卡", {primary: !draft, disabled: !current})}
        ${button("complete-step", complete ? "重新确认完成" : skipped ? "改为已完成" : "已完成这部分", {primary: true})}
        ${definitions.canSkip ? button("skip-step", "暂时跳过") : ""}
      </div>
    </section>`;
  }

  function renderModel() {
    const model = state?.model || {};
    const providers = Array.isArray(model.providers) ? model.providers : [];
    const providerId = modelDraft || model.provider_id || "";
    const taskProviders = Array.isArray(modelTasks?.providers) ? modelTasks.providers : [];
    const tasks = Array.isArray(modelTasks?.tasks) ? modelTasks.tasks : [];
    const taskMarkup = tasks.map(task => {
      const draft = modelTaskDrafts[task.kind] || {};
      const provider = draft.provider ?? task.fields.provider.value;
      const fallback = draft.fallback ?? task.fields.fallback.value;
      const choices = taskProviders.filter(item => task.capabilities.every(capability => item.capabilities.includes(capability)));
      return `<details class="setup-task-route"><summary><strong>${escape(taskLabel(task.kind))}</strong><small>${escape(task.kind)} · ${escape(task.lane)}</small></summary><div class="setup-task-route-fields"><label><span>主 Provider</span><select data-setup-model-task="${escape(task.kind)}" data-setup-model-field="provider" ${busy || !choices.length ? "disabled" : ""}>${choices.map(item => `<option value="${escape(item.id)}" ${provider === item.id ? "selected" : ""}>${escape(item.name || item.id)}</option>`).join("")}</select></label><label><span>备用 Provider</span><select data-setup-model-task="${escape(task.kind)}" data-setup-model-field="fallback" ${busy || !choices.length ? "disabled" : ""}><option value="">不设置</option>${choices.filter(item => item.id !== provider).map(item => `<option value="${escape(item.id)}" ${fallback === item.id ? "selected" : ""}>${escape(item.name || item.id)}</option>`).join("")}</select></label>${button(`save-task:${task.kind}`, "保存路由", {disabled: !choices.length})}</div></details>`;
    }).join("");
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 3</p><h3>配置插件模型</h3>
      <p>选择初始 Provider。初始化后，任务路由可直接使用 AstrBot 中已加载的文本 Provider。</p>
      ${connectionDiagnostic()}
      ${providers.length ? `<label class="setup-model-field"><span>初始主 Provider</span>
        <select name="setup-provider" ${busy ? "disabled" : ""}>
          <option value="">选择 Provider</option>
          ${providers.map(item => `<option value="${escape(item.id)}" ${providerId === item.id ? "selected" : ""}>${escape(item.name)} · ${escape(item.id)}</option>`).join("")}
        </select></label>` : `<p class="setup-inline-error">AstrBot 当前没有已加载的文本 Provider。请先在 AstrBot 的提供方管理中加载模型，再回来刷新。</p>`}
      ${state?.settings_error ? `<p class="setup-inline-error">${escape(state.settings_error)}</p>` : ""}
      ${noticeMarkup()}
      <div class="setup-actions">${button("save-model", state?.prepared ? "保存 Provider 并载入路由" : "初始化并载入任务路由", {primary: true, disabled: !providers.length || !providerId})}${providers.length ? button("refresh", "刷新 Provider") : ""}${state?.prepared ? button("complete-step", "继续到角色设定", {primary: true}) : ""}</div>
      ${state?.prepared ? `<section class="setup-model-routes"><header><div><h4>任务模型路由</h4><p>为对话、主动联系和其他插件任务分别指定主模型及备用模型。</p></div><span>${tasks.length} 项</span></header>${taskMarkup || `<p class="setup-inline-error">${modelTasks ? "当前没有已注册的任务路由。" : "任务路由尚未读取，请刷新后重试。"}</p>`}</section>` : ""}
    </section>`;
  }

  function renderProactiveTest() {
    const test = state?.proactive_test;
    if (state?.ready) {
      const accepting = Boolean(state?.host?.accepting);
      return `<section class="setup-stage setup-finished">
        <p class="setup-kicker">首次连接</p><h3>首次设置已完成</h3>
        <p>核心管理员窗口、模型与初始资料已记录。之后直接使用陪伴小屋和聊天窗口，不需要重新走向导。</p>
        <p class="setup-test-receipt setup-connection-state ${accepting ? "" : "is-stopped"}">${accepting ? "V2 正在接收消息" : "首次设置已保留，当前运行实例尚未接收消息"}</p>
        <p class="setup-test-receipt">${test?.state === "received" ? "你已确认收到测试消息" : "平台已确认发送测试消息"} · ${escape(test?.confirmed_at || test?.finished_at || "")}</p>
        <div class="setup-actions">${accepting ? "" : button("reconnect-host", "重新连接", {primary: true})}${homeButton("进入陪伴小屋", !accepting)}</div>
      </section>`;
    }
    if (test?.state === "started" || test?.state === "unknown") {
      return `<section class="setup-stage">
        <p class="setup-kicker">STEP 6</p><h3>主动测试结果未知</h3>
        <p>主动联系已经经过模型生成与策略检查，但投递结果没有得到确定回执。为避免重复发送，本次不会重放。请到已绑定的私聊核对结果。</p>
        <p class="setup-test-receipt">${test?.state === "started" ? "等待平台确认" : "结果未知"}</p>
        ${noticeMarkup()}
        <div class="setup-actions">${button("confirm-test-received", "已收到测试消息", {primary: true})}${button("refresh", "刷新状态")}</div>
      </section>`;
    }
    if (test?.state === "failed") {
      return `<section class="setup-stage"><p class="setup-kicker">STEP 6</p><h3>主动联系没有送达</h3><p>本次模型或投递链路明确失败，可以检查目标私聊和模型路由后重试。</p>${noticeMarkup()}<label class="setup-opt-in"><input type="checkbox" data-setup-proactive-opt-in ${proactiveOptIn ? "checked" : ""} ${busy ? "disabled" : ""}><span>我同意 V2 向已绑定的管理员私聊发送一次主动联系测试</span></label><div class="setup-actions">${button("proactive-test", "重新运行主动联系", {primary: true, disabled: !proactiveOptIn})}${button("refresh", "刷新状态")}</div></section>`;
    }
    return `<section class="setup-stage">
      <p class="setup-kicker">STEP 6</p><h3>测试主动消息</h3>
      <p>V2 会为当前角色建立一次性联系机会，经过主动联系模型、策略检查和真实投递。只有明确同意后才开始；未知结果不会重复发送。</p>
      <label class="setup-opt-in"><input type="checkbox" data-setup-proactive-opt-in ${proactiveOptIn ? "checked" : ""} ${busy ? "disabled" : ""}><span>我同意 V2 向已绑定的管理员私聊发送一次主动联系测试</span></label>
      ${noticeMarkup()}
      <div class="setup-actions">${button("proactive-test", "运行主动联系测试", {primary: true, disabled: !proactiveOptIn})}</div>
    </section>`;
  }

  function renderUnavailable() {
    return `<section class="setup-stage">
      <p class="setup-kicker">连接状态</p><h3>暂时读不到设置进度</h3>
      <p>${escape(notice || "Dashboard 与 V2 管理接口暂时没有连通。")}</p>
      <div class="setup-actions">${button("refresh", "重新读取", {primary: true})}</div>
    </section>`;
  }

  function render() {
    if (!root) return;
    stopQuickWorkspace();
    if (migrationOnly) {
      root.innerHTML = legacyPanel();
      return;
    }
    if (!state) {
      root.innerHTML = `<div class="setup-shell"><p class="setup-loading">正在读取 V2 设置进度…</p>${renderUnavailable()}</div>`;
      return;
    }
    if (advancedOpen && (state.ready || state.prepared)) {
      root.innerHTML = renderAdvanced();
      mountQuickWorkspace();
      return;
    }
    if (state.ready) {
      root.innerHTML = `<div class="setup-shell setup-complete-shell"><header class="setup-header"><div><span class="setup-kicker">我会永远陪着你 V2.0</span><h2>开始使用</h2></div><div class="setup-header-actions"><button type="button" class="button" data-setup-action="advanced-open">快速配置</button></div></header>${renderProactiveTest()}</div>`;
      return;
    }
    const step = state.step || "binding";
    const content = step === "binding" ? renderBinding()
      : step === "model" ? renderModel()
      : step === "proactive_test" ? renderProactiveTest()
      : renderSection(step);
    const current = stepIndex(step);
    root.innerHTML = `<div class="setup-shell">
      <header class="setup-header"><div><span class="setup-kicker">我会永远陪着你 V2.0</span><h2>开始使用</h2></div>
        <div class="setup-header-actions">${state.prepared ? `<button type="button" class="button" data-setup-action="advanced-open">快速配置</button>` : ""}<span class="setup-step-count">${String(current + 1).padStart(2, "0")} / ${String(ORDER.length).padStart(2, "0")}</span></div></header>
      ${renderRail(step)}<div class="setup-content">${content}</div>
    </div>`;
  }

  async function loadStepData(result) {
    let loadError = "";
    const quickModelsNeeded = advancedOpen && advancedBlock === "runtime" && result?.prepared;
    if (result?.prepared && ((result?.step === "model" && modelDraft) || quickModelsNeeded)) {
      loadError = await refreshModelTasks();
    } else if (!quickModelsNeeded) {
      modelTasks = null;
      modelTasksStatus = "idle";
      modelTasksError = "";
    }
    if (["knowledge", "relationships"].includes(result?.step) && result?.prepared) {
      try { profileState = await api("GET", "/profile"); }
      catch (error) { profileState = null; loadError = errorText(error, "角色档案暂时无法读取。"); }
    } else if (!["knowledge", "relationships"].includes(result?.step)) profileState = null;
    if (loadError) notice = loadError;
  }

  async function refresh() {
    const ticket = ++generation;
    try {
      const result = await api("GET", "/status");
      if (ticket !== generation) return;
      state = result;
      /* 成功读到新状态后，上一轮网络失败提示必须消失；子步骤若读失败，
         loadStepData() 会再写入更具体的提示。 */
      notice = "";
      modelDraft = result?.model?.provider_id || "";
      await loadStepData(result);
      render();
      if (result?.proactive_test?.state === "started") void watchProactive();
    } catch (error) {
      if (ticket !== generation) return;
      state = null;
      notice = errorText(error, "V2 管理接口暂时没有连通。");
      render();
    }
  }

  async function generateProfileDraft() {
    const target = state?.step === "relationships" ? "relationship_profile" : "role_profile";
    const productApi = product();
    const bridge = productApi?.bridgeNow?.() || (productApi?.bridgeFor ? await productApi.bridgeFor() : window.AstrBotPluginPage);
    if (!bridge?.apiPost) throw new Error("Dashboard 页面接口尚未连接。");
    const route = productApi.relative("/astrbot_plugin_private_companion_v2/setup/profile-draft");
    const supplement = profileSupplement[target] || "";
    let timer;
    try {
      const response = await Promise.race([
        bridge.apiPost(route, {target, supplement}),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(Object.assign(new Error("人格草稿生成超时，请保留补充内容后重试。"), {code: "role_profile_draft_timeout"})), 120000);
        }),
      ]);
      const payload = productApi.unwrap(response);
      if (payload.target !== target || !payload.draft?.fields) throw new Error("草稿目标或内容无效，请重新读取后生成。");
      profileDraftTarget = target;
      profileDraft = payload.draft;
      profileFieldDrafts = {};
      profileSelected = new Set(Object.entries(payload.draft.fields)
        .filter(([, value]) => typeof value === "string" && value.trim()).map(([name]) => name));
      profileNotes = [...(payload.draft.notes || [])];
      profileDraft = {...payload.draft, source: payload.source, knowledge: payload.knowledge,
        limits: payload.limits, total_limit: payload.total_limit};
      notice = target === "role_profile" ? "角色档案草稿已生成，请检查推断和世界资料后再保存。" : "熟人卡草稿已生成，请核对称呼、关系与相处方式后再保存。";
    } finally { clearTimeout(timer); }
  }

  async function saveProfileDraft() {
    const target = state?.step === "relationships" ? "relationship_profile" : "role_profile";
    const current = profileState?.[target];
    if (!current?.edit_token || profileDraftTarget !== target || !profileDraft?.fields) throw new Error("当前草稿或配置版本已变化，请重新读取后生成。");
    const changes = {};
    for (const name of profileSelected) {
      const value = profileFieldDrafts[name] ?? profileDraft.fields[name] ?? "";
      if (!String(value).trim()) continue;
      if (!profileOverwrite && String(current.settings?.[name] || "").trim()) continue;
      changes[name] = value;
    }
    if (!Object.keys(changes).length) throw new Error(profileOverwrite ? "先选择至少一个有内容的字段。" : "所选字段已有内容；打开“覆盖已有字段”后再保存。");
    await api("POST", "/profile/save", {target, operation_key: operationKey("setup-profile"),
      edit_token: current.edit_token, changes});
    profileState = await api("GET", "/profile");
    profileSelected = new Set();
    notice = `已保存 ${Object.keys(changes).length} 项${target === "role_profile" ? "角色设定" : "熟人卡资料"}。`;
  }

  async function saveModelTask(kind) {
    const route = currentRoleModelRoute();
    syncModelTasksScope(route.scope);
    if (modelTasksStatus !== "loaded") throw Object.assign(new Error("model_route_scope_changed"), {code: "model_route_scope_changed"});
    const task = modelTasks?.tasks?.find(item => item.kind === kind);
    if (!task) throw new Error("没有读到这项模型任务，请刷新后重试。");
    const draft = modelTaskDrafts[kind] || {};
    const provider = draft.provider ?? task.fields.provider.value;
    const fallback = draft.fallback ?? task.fields.fallback.value;
    const saved = await product().request("POST", route.path + "/configure", {
      kind, operation_key: operationKey("setup-model-route"), edit_token: task.edit_token,
      changes: {provider, fallback}, reset: [],
    });
    if (saved?.task?.kind !== kind || typeof saved.replayed !== "boolean") {
      throw Object.assign(new Error("invalid_response"), {code: "invalid_response"});
    }
    if (route.scope !== currentModelScopeKey()) {
      syncModelTasksScope();
      notice = "原角色模型路由已保存；当前小屋已切换到另一个角色。";
      return;
    }
    modelTasks = {...modelTasks, tasks: modelTasks.tasks.map(item => item.kind === kind ? saved.task : item)};
    modelTaskDrafts[kind] = {};
    notice = saved.replayed ? `${taskLabel(kind)}模型路由原保存已确认。` : `${taskLabel(kind)}模型路由已保存。`;
  }

  async function watchProactive() {
    if (proactiveWatcher) return;
    proactiveWatcher = true;
    try {
      for (let attempt = 0; attempt < 205; attempt += 1) {
        const result = await api("GET", "/status");
        state = result;
        render();
        const current = result?.proactive_test?.state;
        if (result?.ready || current !== "started") {
          if (current === "failed") proactiveOptIn = false;
          notice = current === "delivered" || current === "received" ? "V2 主动联系已完成，收到真实投递回执。"
            : current === "failed" ? "主动联系链路明确失败，可以检查配置后重试。"
            : "投递结果未知；请核对目标私聊，不要再次发送。";
          render();
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 750));
      }
    } catch (error) {
      notice = errorText(error, "主动联系状态暂时无法读取，请稍后刷新。");
      render();
    } finally { proactiveWatcher = false; }
  }

  async function runLegacy(action) {
    legacyError = "";
    legacyDataError = "";
    migrationProgress = ({
      "legacy-scan": "正在只读检查 V1 来源…",
      "legacy-plan": "正在试算可转换的配置…",
      "legacy-apply": "正在写入 V2 并核对迁移结果…",
      "legacy-data-plan": "正在清点 V1 文件与独立记忆库；数据较多时可能需要几分钟…",
      "legacy-data-apply": "正在导入所选资料并核对结果…",
      "legacy-data-batch-plan": "正在逐个试算已映射的人格目的地…",
      "legacy-data-batch-apply": "正在按顺序导入已确认的人格目的地…",
      "legacy-group-data-plan": "正在试算所选群资料…",
      "legacy-group-data-apply": "正在导入所选群资料并核对结果…",
    })[action] || "";
    render();
    if (action === "legacy-scan") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      legacyFinding = await migrationRequest("GET", legacyRoute(), legacyQuery());
      legacyPlan = null;
      legacyResult = null;
    } else if (action === "legacy-plan") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      if (!legacyApi || !legacyFinding) throw new Error("先检查 V1 来源，再试算迁移。");
      legacyPlan = await migrationRequest("GET", legacyRoute("/plan"), legacyQuery());
      legacyResult = null;
    } else if (action === "legacy-apply") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      if (!legacyApi || !legacyPlan?.plan_token) throw new Error("先完成迁移试算，再执行写入。");
      legacyResult = await migrationRequest("POST", legacyApi + "/apply", {
        plan_token: legacyPlan.plan_token, configuration_scope: legacyConfigScope,
        ...(legacyRootDraft.trim() ? {v1_root: legacyRootDraft.trim()} : {})});
      notice = legacyResult?.restart_required
        ? "迁移设置已保存，请重启插件使插件级配置生效。"
        : "V1 配置已写入当前 V2 目标。";
      legacyFinding = null;
      legacyPlan = null;
    } else if (action === "legacy-data-plan") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      legacyDataPlan = await migrationRequest("GET", legacyRoute("/data-plan"), legacyDataQuery());
      legacyMemoryPlanDirty = false;
      seedMemoryGroupMappings(legacyDataPlan);
      syncLegacyPersonaMappings(legacyDataPlan.persona_sources || []);
      legacyDataResult = null;
      if (!legacyArchiveCanApply(legacyDataPlan.archive)) {
        legacyImportArchive = false;
      }
    } else if (action === "legacy-data-apply") {
      if (!legacyAddress()) throw new Error("先选择有迁移接口的 V2 目标与人格。");
      legacyApi = legacyAddress();
      if (!legacyDataPlan?.plan_token) throw new Error("先完成数据试算，再执行导入。");
      legacyDataResult = await migrationRequest("POST", legacyApi + "/data-apply", {
        plan_token: legacyDataPlan.plan_token,
        import_reactions: legacyImportReactions,
        import_group_network: legacyImportGroupNetwork,
        confirm_member_ids: legacyConfirmMemberIds,
        import_journals: legacyImportJournals,
        confirm_persona_mapping: legacyConfirmPersonaMapping,
        import_worldbook: legacyImportWorldbook,
        import_reference_images: legacyImportReferenceImages,
        import_wardrobe_items: legacyImportWardrobeItems,
        confirm_reference_persona_mapping: legacyConfirmReferencePersonaMapping,
        import_memory_database: Boolean(legacyImportMemoryDatabase
          && legacyMemoryArchiveCanApply(legacyDataPlan?.memory_database)),
        memory_owner_ids: [...legacyMemoryOwnerIds].sort(),
        memory_group_mappings: [...legacyMemoryGroupMappings.entries()].sort(([left], [right]) => left.localeCompare(right))
          .map(([owner_id, target]) => ({owner_id, target_id: target.target_id, role_id: target.role_id})),
        confirm_memory_mapping: legacyConfirmMemoryMapping,
        import_archive: Boolean(legacyImportArchive && legacyArchiveCanApply(legacyDataPlan?.archive)),
        source_persona_id: legacyDataPersonaId,
        source_group_id: legacyDataGroupId,
        ...(legacyRootDraft.trim() ? {v1_root: legacyRootDraft.trim()} : {})});
      legacyImportGroupNetwork = false;
      legacyImportArchive = false;
      legacyImportMemoryDatabase = false;
      legacyDataPlan = await migrationRequest("GET", legacyRoute("/data-plan"), legacyDataQuery());
      syncLegacyPersonaMappings(legacyDataPlan.persona_sources || []);
      legacyDataError = "";
    } else if (action === "legacy-data-batch-plan") {
      const personas = (legacyDataPlan?.persona_sources || []).filter(item => item.state === "ready");
      if (!personas.length) throw new Error("没有可安全读取的 V1 人格档案。");
      syncLegacyPersonaMappings(legacyDataPlan.persona_sources || []);
      const assignments = legacyPersonaAssignments(personas);
      if (hasDuplicateLegacyPersonaRoles(assignments)) {
        throw new Error("同一个 V2 私聊目标与角色只能映射一次，请先移除重复项。");
      }
      const undecided = personas.some(item => {
        const mapping = legacyPersonaMappings.get(item.persona_id || "");
        return !mapping?.skip && (!mapping?.destinations.length
          || mapping.destinations.some(destination => !destination.target_id || !destination.role_id
            || !legacyPersonaRole(destination)));
      });
      if (undecided) throw new Error("请为每个人格至少添加一个明确选择的 V2 目的地，或勾选“明确跳过此人格”。");
      if (!assignments.length) throw new Error("至少明确添加一个目的地后才能试算。");
      legacyPersonaBatchError = "";
      const sourceById = new Map(personas.map(item => [item.persona_id || "", item]));
      for (let index = 0; index < assignments.length; index += 1) {
        const {sourceId, destination} = assignments[index];
        const role = legacyPersonaRole(destination);
        destination.plan = null;
        destination.result = null;
        destination.error = "";
        destination.status = "planning";
        legacyPersonaBatchProgress = `正在试算第 ${index + 1} / ${assignments.length} 个目的地：${sourceById.get(sourceId)?.label || "主角色"}`;
        render();
        try {
          const route = product().relative(role.legacy_api) + "/data-plan";
          const plan = await migrationRequest("GET", route, legacyPersonaQuery(sourceId));
          if (!plan?.plan_token || plan.source_persona_id !== sourceId
              || typeof plan.archive?.fingerprint !== "string" || !plan.archive.fingerprint) {
            throw new Error("目标返回的试算计划不完整，请重新读取目标状态。");
          }
          destination.plan = plan;
          destination.status = "ready";
        } catch (error) {
          destination.status = "error";
          destination.error = errorText(error, "该目的地试算失败");
        }
      }
      const planned = assignments.map(item => item.destination);
      const archiveFingerprints = new Set(planned.filter(item => item.plan).map(item => item.plan.archive.fingerprint));
      if (archiveFingerprints.size > 1) {
        for (const destination of planned) {
          destination.plan = null;
          destination.status = "stale";
          destination.error = "试算期间 V1 来源清单发生变化";
        }
        legacyPersonaBatchError = "试算期间 V1 文件清单发生变化；没有执行导入，请重新试算全部目的地。";
      } else if (planned.some(item => !item.plan)) {
        legacyPersonaBatchError = "部分目的地试算失败；请先修正目标或连接问题，再重新试算。";
      } else {
        legacyPersonaBatchError = "";
      }
      legacyPersonaBatchProgress = `已试算 ${planned.filter(item => item.plan).length} / ${assignments.length} 个目的地；可逐项核对导入范围。`;
    } else if (action === "legacy-data-batch-apply") {
      const personas = (legacyDataPlan?.persona_sources || []).filter(item => item.state === "ready");
      const assignments = legacyPersonaAssignments(personas);
      if (!assignments.length || hasDuplicateLegacyPersonaRoles(assignments)) {
        throw new Error("请先为每个人格完成唯一的目标角色映射和试算。");
      }
      if (personas.some(item => {
        const mapping = legacyPersonaMappings.get(item.persona_id || "");
        return !mapping?.skip && (!mapping?.destinations.length
          || mapping.destinations.some(destination => !destination.plan?.plan_token
            || destination.error || !legacyPersonaRole(destination)));
      })) throw new Error("请先为全部未跳过的人格的每个目的地完成试算和复核。");
      const runnable = assignments.filter(item => legacyPersonaBatchCanApply(item.destination));
      if (!runnable.length) throw new Error("没有已勾选且可导入的数据项。");
      legacyPersonaBatchError = "";
      for (let index = 0; index < runnable.length; index += 1) {
        const {sourceId, persona, destination} = runnable[index];
        const role = legacyPersonaRole(destination);
        destination.status = "applying";
        destination.error = "";
        legacyPersonaBatchProgress = `正在执行第 ${index + 1} / ${runnable.length} 个目的地：${persona.label || "主角色"}`;
        render();
        const route = product().relative(role.legacy_api);
        let applyStarted = false;
        try {
          const fresh = await migrationRequest("GET", route + "/data-plan", legacyPersonaQuery(sourceId));
          if (!fresh?.plan_token || fresh.source_persona_id !== sourceId
              || fresh.source_fingerprint !== destination.plan.source_fingerprint
              || fresh.archive?.fingerprint !== destination.plan.archive?.fingerprint) {
            destination.plan = null;
            destination.status = "stale";
            destination.error = "V1 来源在试算后发生变化，请重新试算";
            legacyPersonaBatchError = `${persona.label || "该人格"} 的来源已变化；本项目的 V2 目标及后续目的地未执行。`;
            break;
          }
          destination.plan = fresh;
          const worldbook = fresh.worldbook || {};
          const journals = fresh.journals || {};
          const references = fresh.reference_images || {};
          const wardrobe = fresh.wardrobe_items || {};
          const worldbookReady = destination.include_worldbook && (
            (Number(worldbook.general_count) > 0 && !worldbook.base_entries_matches)
            || (destination.confirm_member_ids && Number(worldbook.member_count) > 0
              && !worldbook.base_members_matches));
          applyStarted = true;
          const result = await migrationRequest("POST", route + "/data-apply", {
            plan_token: fresh.plan_token,
            import_reactions: destination.include_reactions && Number(fresh.reaction_assets?.batch_count) > 0,
            import_group_network: false,
            confirm_member_ids: destination.confirm_member_ids,
            import_journals: destination.include_journals && Number(journals.batch_count) > 0,
            confirm_persona_mapping: destination.confirm_persona_mapping,
            import_worldbook: Boolean(worldbookReady),
            import_reference_images: destination.include_reference_images
              && Number(references.batch_count) > 0,
            import_wardrobe_items: destination.include_wardrobe_items
              && Number(wardrobe.batch_count) > 0,
            confirm_reference_persona_mapping: destination.confirm_reference_persona_mapping,
            import_memory_database: false,
            import_archive: false,
            source_persona_id: sourceId,
            source_group_id: "",
            ...(legacyRootDraft.trim() ? {v1_root: legacyRootDraft.trim()} : {})});
          if (!result || result.source_persona_id !== sourceId || !Array.isArray(result.errors)) {
            throw new Error("目标未返回可核对的导入回执");
          }
          destination.result = result;
          const remaining = (Number(result.reaction_remaining) || 0)
            + (Number(result.journal_remaining) || 0)
            + (Number(result.journal_derivatives_remaining) || 0)
            + (Number(result.reference_images?.reference_remaining) || 0)
            + (Number(result.reference_images?.wardrobe_remaining) || 0);
          if (result.errors.length) {
            destination.status = "error";
            destination.error = `${result.errors.length} 项未成功，已停止后续目的地`;
            legacyPersonaBatchError = `${persona.label || "该人格"} 的目的地导入有失败项；本项目的 V2 目标及后续目的地未执行。`;
            break;
          }
          destination.status = remaining ? "partial" : "imported";
        } catch (error) {
          destination.status = applyStarted ? "unknown" : "error";
          if (applyStarted) destination.plan = null;
          destination.error = errorText(error, applyStarted ? "导入响应未确认" : "试算复核失败");
          legacyPersonaBatchError = applyStarted
            ? `${persona.label || "该人格"} 的导入结果未确认；本项目的 V2 目标及后续目的地未执行，请先核对当前目标。`
            : `${persona.label || "该人格"} 的来源复核失败；本项目的 V2 目标及后续目的地未执行。`;
          break;
        }
      }
      legacyPersonaBatchProgress = "本轮目的地执行已停止；各目标结果已分别保留。若有分批剩余，请重新试算后继续。";
    } else if (action === "legacy-group-data-plan") {
      const choices = legacyGroupSelection();
      if (!choices.api || !choices.persona || !legacyDataGroupId) {
        throw new Error("请先选定可读取的 V1 人格和 V1 群记录，再明确选择 V2 群目标与角色。");
      }
      const query = legacyPersonaQuery(legacyDataPersonaId);
      query.source_group_id = legacyDataGroupId;
      legacyGroupPlan = await migrationRequest("GET", choices.api + "/plan", query);
      legacyGroupResult = null;
      legacyGroupError = "";
      legacyGroupConfirmMapping = false;
      legacyGroupConfirmMemberIds = false;
    } else if (action === "legacy-group-data-apply") {
      const choices = legacyGroupSelection();
      if (!choices.api || !legacyGroupPlan?.plan_token) throw new Error("先完成 V2 群目标的映射试算。");
      legacyGroupResult = await migrationRequest("POST", choices.api + "/apply", {
        plan_token: legacyGroupPlan.plan_token,
        source_persona_id: legacyDataPersonaId,
        source_group_id: legacyDataGroupId,
        import_group_network: Boolean(legacyGroupImportNetwork && legacyGroupPlan.source_group_network),
        import_group_worldbook: Boolean(legacyGroupImportWorldbook
          && Number(legacyGroupPlan.group_worldbook?.entries) + Number(legacyGroupPlan.group_worldbook?.members) > 0),
        confirm_member_ids: legacyGroupConfirmMemberIds,
        confirm_group_mapping: legacyGroupConfirmMapping,
        ...(legacyRootDraft.trim() ? {v1_root: legacyRootDraft.trim()} : {})});
      legacyGroupError = "";
    }
    migrationProgress = "";
  }

  async function act(action) {
    if (busy) return;
    busy = true;
    notice = "";
    render();
    try {
      if (action === "confirm-binding") {
        await api("POST", "/binding/confirm", {});
      } else if (action === "prepare") {
        await api("POST", "/prepare", {});
      } else if (action === "save-model") {
        await api("POST", "/model", {provider_id: modelDraft});
        modelTaskDrafts = {};
        notice = "已初始化模型；任务路由可直接选择 AstrBot 当前已加载的 Provider。";
      } else if (action.startsWith("save-task:")) {
        await saveModelTask(action.slice("save-task:".length));
      } else if (action === "generate-profile") {
        await generateProfileDraft();
      } else if (action === "save-profile") {
        await saveProfileDraft();
      } else if (action === "complete-step" || action === "skip-step") {
        await api("POST", "/complete", {step: state.step, skipped: action === "skip-step"});
      } else if (action === "proactive-test") {
        await api("POST", "/proactive-test", {enable_proactive: true});
        proactiveOptIn = false;
        notice = "主动联系已启动，正在等待模型生成、策略检查和投递回执。";
      } else if (action === "confirm-test-received") {
        await api("POST", "/proactive-test/confirm", {attempt_id: state.proactive_test.attempt_id});
        notice = "已记录你收到测试消息，首次设置已完成。";
      } else if (action === "reconnect-host") {
        await api("POST", "/host/start", {});
        notice = "V2 已重新连接并开始接收消息。";
      } else if (["legacy-scan", "legacy-plan", "legacy-apply", "legacy-data-plan", "legacy-data-apply",
        "legacy-data-batch-plan", "legacy-data-batch-apply", "legacy-group-data-plan",
        "legacy-group-data-apply"].includes(action)) {
        await runLegacy(action);
      }
      if (migrationOnly && action.startsWith("legacy-")) return;
      if (action === "refresh") {
        await refresh();
      } else {
        const result = await api("GET", "/status");
        state = result;
        modelDraft = result?.model?.provider_id || "";
        await loadStepData(result);
        if (result.ready) notice = "";
        render();
        if (result?.proactive_test?.state === "started") void watchProactive();
      }
    } catch (error) {
      migrationProgress = "";
      if (action.startsWith("legacy-")) {
        const message = errorText(error, "V1 迁移未完成，请核对当前 V2 目标后重试。");
        if (action.startsWith("legacy-data-")) {
          legacyDataError = message;
          if (action === "legacy-data-apply") legacyDataPlan = null;
        } else if (action.startsWith("legacy-group-data-")) {
          legacyGroupError = message;
          if (action === "legacy-group-data-apply") legacyGroupPlan = null;
        } else {
          legacyError = message;
        }
        if (action === "legacy-apply") legacyPlan = null;
      }
      notice = errorText(error, "操作未完成，请重新读取状态。");
      if (!migrationOnly) {
        try { state = await api("GET", "/status"); } catch { state = null; }
      }
      render();
    } finally {
      busy = false;
      if (root) render();
    }
  }

  function onClick(event) {
    const addDestination = event.target.closest?.("[data-setup-legacy-batch-add]");
    if (addDestination) {
      const sourceId = addDestination.dataset.setupLegacyBatchAdd || "";
      const mapping = legacyPersonaMappings.get(sourceId);
      if (mapping && !mapping.skip && !busy) {
        mapping.destinations.push(newLegacyPersonaDestination());
        legacyPersonaBatchError = "";
        render();
      }
      return;
    }
    const removeDestination = event.target.closest?.("[data-setup-legacy-batch-remove]");
    if (removeDestination) {
      const sourceId = removeDestination.dataset.setupLegacyBatchRemove || "";
      const mapping = legacyPersonaMappings.get(sourceId);
      if (mapping && !busy) {
        mapping.destinations = mapping.destinations.filter(item =>
          item.destination_id !== removeDestination.dataset.destinationId);
        legacyPersonaBatchError = "";
        render();
      }
      return;
    }
    const legacyAction = event.target.closest?.("[data-setup-legacy-action]")?.dataset.setupLegacyAction;
    if (legacyAction) { act(legacyAction); return; }
    const advancedBlockButton = event.target.closest?.("[data-setup-advanced-block]");
    if (advancedBlockButton) {
      advancedBlock = ADVANCED_BLOCKS.some(item => item.id === advancedBlockButton.dataset.setupAdvancedBlock)
        ? advancedBlockButton.dataset.setupAdvancedBlock : "understanding";
      render();
      return;
    }
    const action = event.target.closest?.("[data-setup-action]")?.dataset.setupAction;
    if (action === "retry-model-routes") { void retryQuickModels(); return; }
    if (action === "advanced-open" && (state?.ready || state?.prepared)) {
      advancedOpen = true;
      render();
      return;
    }
    if (action === "advanced-close") {
      advancedOpen = false;
      render();
      return;
    }
    if (action) act(action);
  }

  function onChange(event) {
    const input = event.target;
    if (input?.dataset?.setupLegacy === "target") {
      legacyTargetId = input.value;
      legacyRoleId = "";
      legacyApi = "";
      legacyFinding = legacyPlan = legacyResult = null;
      legacyDataPlan = legacyDataResult = null;
      legacyDataGroupId = "";
      legacyDataPersonaId = "";
      legacyImportWorldbook = false;
      legacyImportReferenceImages = false;
      legacyImportWardrobeItems = false;
      legacyConfirmReferencePersonaMapping = false;
      legacyConfirmMemberIds = false;
      legacyConfirmPersonaMapping = false;
      legacyError = "";
      legacyDataError = "";
      render();
    }
    if (input?.dataset?.setupLegacy === "root") {
      legacyRootDraft = input.value;
      legacyFinding = legacyPlan = legacyResult = null;
      legacyDataPlan = legacyDataResult = null;
      legacyConfirmReferencePersonaMapping = false;
      legacyMemoryOwnerIds = new Set();
      legacyMemoryGroupMappings = new Map();
      legacyMemoryGroupMappingSeeded = false;
      legacyMemoryPlanDirty = false;
      legacyConfirmMemoryMapping = false;
      legacyPersonaMappings = new Map();
      legacyPersonaBatchError = "";
      legacyPersonaBatchProgress = "";
      legacyGroupPlan = legacyGroupResult = null;
      legacyGroupError = "";
      legacyError = "";
      legacyDataError = "";
    }
    if (input?.dataset?.setupLegacy === "configuration-scope") {
      legacyConfigScope = input.value === "all" ? "all" : "proactive";
      legacyFinding = legacyPlan = legacyResult = null;
      legacyError = "";
    }
    if (input?.dataset?.setupLegacy === "role") {
      legacyRoleId = input.value;
      legacyApi = "";
      legacyFinding = legacyPlan = legacyResult = null;
      legacyDataPlan = legacyDataResult = null;
      legacyDataGroupId = "";
      legacyDataPersonaId = "";
      legacyImportWorldbook = false;
      legacyImportReferenceImages = false;
      legacyImportWardrobeItems = false;
      legacyConfirmReferencePersonaMapping = false;
      legacyConfirmMemberIds = false;
      legacyConfirmPersonaMapping = false;
      legacyError = "";
      legacyDataError = "";
      render();
    }
    if (input?.dataset?.setupLegacy === "data-group") {
      legacyDataGroupId = input.value;
      legacyImportGroupNetwork = Boolean(input.value && (legacyDataPlan?.group_networks || []).some(item => item.source_group_id === input.value));
      legacyConfirmMemberIds = false;
      legacyDataPlan = legacyDataResult = null;
      legacyGroupPlan = legacyGroupResult = null;
      legacyGroupError = "";
      legacyGroupConfirmMapping = false;
      legacyGroupConfirmMemberIds = false;
      legacyDataError = "";
      render();
    }
    if (input?.dataset?.setupLegacy === "data-persona") {
      legacyDataPersonaId = input.value;
      legacyDataPlan = legacyDataResult = null;
      legacyGroupPlan = legacyGroupResult = null;
      legacyGroupError = "";
      legacyGroupConfirmMapping = false;
      legacyGroupConfirmMemberIds = false;
      legacyImportJournals = false;
      legacyConfirmPersonaMapping = false;
      legacyImportReferenceImages = false;
      legacyImportWardrobeItems = false;
      legacyConfirmReferencePersonaMapping = false;
      legacyDataError = "";
      render();
    }
    if (input?.dataset?.setupLegacy === "group-target") {
      legacyGroupTargetId = input.value;
      legacyGroupRoleId = "";
      legacyGroupPlan = legacyGroupResult = null;
      legacyGroupError = "";
      legacyGroupConfirmMapping = false;
      legacyGroupConfirmMemberIds = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "group-role") {
      legacyGroupRoleId = input.value;
      legacyGroupPlan = legacyGroupResult = null;
      legacyGroupError = "";
      legacyGroupConfirmMapping = false;
      legacyGroupConfirmMemberIds = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "group-import-network") {
      legacyGroupImportNetwork = Boolean(input.checked);
      legacyGroupConfirmMemberIds = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "group-import-worldbook") {
      legacyGroupImportWorldbook = Boolean(input.checked);
      legacyGroupConfirmMemberIds = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "group-confirm-mapping") {
      legacyGroupConfirmMapping = Boolean(input.checked);
      render();
    }
    if (input?.dataset?.setupLegacy === "group-confirm-member-ids") {
      legacyGroupConfirmMemberIds = Boolean(input.checked);
      render();
    }
    if (input?.dataset?.setupLegacyBatchTarget !== undefined) {
      const mapping = legacyPersonaMappings.get(input.dataset.personaId || "");
      const destination = mapping?.destinations.find(item => item.destination_id === input.dataset.destinationId);
      if (destination) {
        destination.target_id = input.value;
        destination.role_id = "";
        destination.include_reactions = true;
        destination.include_worldbook = false;
        destination.include_journals = false;
        destination.confirm_member_ids = false;
        destination.confirm_persona_mapping = false;
        destination.include_reference_images = false;
        destination.include_wardrobe_items = false;
        destination.confirm_reference_persona_mapping = false;
        destination.plan = destination.result = null;
        destination.status = input.value ? "mapped" : "unmapped";
        destination.error = "";
        legacyPersonaBatchError = "";
      }
      render();
    }
    if (input?.dataset?.setupLegacyBatchRole !== undefined) {
      const mapping = legacyPersonaMappings.get(input.dataset.personaId || "");
      const destination = mapping?.destinations.find(item => item.destination_id === input.dataset.destinationId);
      if (destination) {
        if (legacyPersonaRoleTaken(destination.target_id, input.value,
            input.dataset.personaId || "", destination.destination_id)) {
          destination.role_id = "";
          destination.plan = destination.result = null;
          destination.status = "unmapped";
          destination.error = "该 V2 目标角色已映射到另一个目的地，请选另一个角色。";
          legacyPersonaBatchError = "已阻止重复的 V2 目标角色映射。";
        } else {
          destination.role_id = input.value;
          destination.include_reactions = true;
          destination.include_worldbook = false;
          destination.include_journals = false;
          destination.confirm_member_ids = false;
          destination.confirm_persona_mapping = false;
          destination.include_reference_images = false;
          destination.include_wardrobe_items = false;
          destination.confirm_reference_persona_mapping = false;
          destination.plan = destination.result = null;
          destination.status = input.value ? "mapped" : "unmapped";
          destination.error = "";
          legacyPersonaBatchError = "";
        }
      }
      render();
    }
    if (input?.dataset?.setupLegacyBatchSkip !== undefined) {
      const mapping = legacyPersonaMappings.get(input.dataset.personaId || "");
      if (mapping) {
        mapping.skip = Boolean(input.checked);
        for (const destination of mapping.destinations) {
          destination.plan = destination.result = null;
          destination.status = destination.target_id && destination.role_id ? "mapped" : "unmapped";
          destination.error = "";
        }
        legacyPersonaBatchError = "";
      }
      render();
    }
    if (input?.dataset?.setupLegacyBatchOption) {
      const mapping = legacyPersonaMappings.get(input.dataset.personaId || "");
      const destination = mapping?.destinations.find(item => item.destination_id === input.dataset.destinationId);
      if (destination) {
        const property = {
          reactions: "include_reactions", worldbook: "include_worldbook", journals: "include_journals",
          "confirm-members": "confirm_member_ids", "confirm-journals": "confirm_persona_mapping",
          "reference-images": "include_reference_images", "wardrobe-items": "include_wardrobe_items",
          "confirm-reference-persona": "confirm_reference_persona_mapping",
        }[input.dataset.setupLegacyBatchOption];
        if (property) destination[property] = Boolean(input.checked);
        if (input.dataset.setupLegacyBatchOption === "journals" && !input.checked) {
          destination.confirm_persona_mapping = false;
        }
        if (input.dataset.setupLegacyBatchOption === "worldbook" && !input.checked) {
          destination.confirm_member_ids = false;
        }
        if (input.dataset.setupLegacyBatchOption === "reference-images"
            || input.dataset.setupLegacyBatchOption === "wardrobe-items") {
          destination.confirm_reference_persona_mapping = false;
        }
        if (input.dataset.setupLegacyBatchOption === "confirm-reference-persona" && !input.checked) {
          destination.confirm_reference_persona_mapping = false;
        }
      }
      render();
    }
    if (input?.dataset?.setupLegacy === "import-reactions") {
      legacyImportReactions = input.checked;
      render();
    }
    if (input?.dataset?.setupLegacy === "import-group-network") {
      legacyImportGroupNetwork = input.checked;
      legacyConfirmMemberIds = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "import-worldbook") {
      legacyImportWorldbook = input.checked;
      legacyConfirmMemberIds = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "import-journals") {
      legacyImportJournals = input.checked;
      legacyConfirmPersonaMapping = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "import-reference-images") {
      legacyImportReferenceImages = Boolean(input.checked);
      legacyConfirmReferencePersonaMapping = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "import-wardrobe-items") {
      legacyImportWardrobeItems = Boolean(input.checked);
      legacyConfirmReferencePersonaMapping = false;
      render();
    }
    if (input?.dataset?.setupLegacy === "confirm-reference-persona-mapping") {
      legacyConfirmReferencePersonaMapping = Boolean(input.checked);
      render();
    }
    if (input?.dataset?.setupLegacy === "import-memory-database") {
      legacyImportMemoryDatabase = input.checked;
      render();
    }
    if (input?.dataset?.setupLegacy === "memory-owner") {
      const ownerId = input.dataset.ownerId;
      if (input.checked && legacyMemoryOwnerIds.size >= MAX_LEGACY_MEMORY_OWNER_SELECTION) {
        input.checked = false;
      } else if (input.checked) {
        legacyMemoryOwnerIds.add(ownerId);
      } else {
        legacyMemoryOwnerIds.delete(ownerId);
      }
      legacyMemoryPlanDirty = true;
      legacyConfirmMemoryMapping = false;
      legacyDataResult = null;
      render();
    }
    if (input?.dataset?.setupLegacy === "memory-group-target") {
      const ownerId = input.dataset.ownerId;
      if (!input.value) {
        legacyMemoryGroupMappings.delete(ownerId);
      } else {
        const selected = JSON.parse(input.value);
        legacyMemoryGroupMappings.set(ownerId, selected);
      }
      legacyMemoryPlanDirty = true;
      legacyConfirmMemoryMapping = false;
      legacyDataResult = null;
      render();
    }
    if (input?.dataset?.setupLegacy === "confirm-memory-mapping") {
      legacyConfirmMemoryMapping = Boolean(input.checked);
      render();
    }
    if (input?.dataset?.setupLegacy === "confirm-member-ids") {
      legacyConfirmMemberIds = input.checked;
      render();
    }
    if (input?.dataset?.setupLegacy === "confirm-persona-mapping") {
      legacyConfirmPersonaMapping = input.checked;
      render();
    }
    if (input?.name === "setup-provider") {
      modelDraft = input.value;
      render();
    }
    if (input?.dataset?.setupModelTask && input?.dataset?.setupModelField) {
      const {setupModelTask: kind, setupModelField: field} = input.dataset;
      modelTaskDrafts[kind] = {...(modelTaskDrafts[kind] || {}), [field]: input.value};
      if (field === "provider" && modelTaskDrafts[kind].fallback === input.value) {
        modelTaskDrafts[kind].fallback = "";
      }
      render();
    }
    if (input?.dataset?.profileSupplement !== undefined) {
      const target = state?.step === "relationships" ? "relationship_profile" : "role_profile";
      profileSupplement[target] = input.value;
    }
    if (input?.dataset?.profileField) {
      profileFieldDrafts[input.dataset.profileField] = input.value;
    }
    if (input?.dataset?.profileSelect) {
      if (input.checked) profileSelected.add(input.dataset.profileSelect);
      else profileSelected.delete(input.dataset.profileSelect);
      render();
    }
    if (input?.dataset?.profileOverwrite !== undefined) {
      profileOverwrite = Boolean(input.checked);
      render();
    }
    if (input?.dataset?.setupProactiveOptIn !== undefined) {
      proactiveOptIn = Boolean(input.checked);
      render();
    }
  }

  function mount(node, {migration = false} = {}) {
    unmount();
    root = node;
    migrationOnly = migration;
    root.addEventListener("click", onClick);
    root.addEventListener("change", onChange);
    state = null;
    notice = "";
    modelDraft = "";
    modelTasks = null;
    modelTasksStatus = "idle";
    modelTasksError = "";
    modelTasksPromise = null;
    modelTasksScopeKey = null;
    modelTaskDrafts = {};
    profileState = null;
    profileDraft = null;
    profileDraftTarget = "role_profile";
    profileFieldDrafts = {};
    profileSelected = new Set();
    profileSupplement = {role_profile: "", relationship_profile: ""};
    profileOverwrite = false;
    profileNotes = [];
    proactiveOptIn = false;
    advancedOpen = false;
    advancedBlock = "understanding";
    legacyTargetId = legacyRoleId = legacyApi = "";
    legacyFinding = legacyPlan = legacyResult = null;
    legacyDataPlan = legacyDataResult = null;
    legacyPersonaMappings = new Map();
    legacyPersonaBatchError = "";
    legacyPersonaBatchProgress = "";
    legacyGroupTargetId = legacyGroupRoleId = "";
    legacyGroupPlan = legacyGroupResult = null;
    legacyGroupError = "";
    legacyGroupImportNetwork = legacyGroupImportWorldbook = true;
    legacyGroupConfirmMapping = legacyGroupConfirmMemberIds = false;
    legacyDataGroupId = "";
    legacyDataPersonaId = "";
    legacyImportReactions = true;
    legacyImportGroupNetwork = false;
    legacyImportWorldbook = false;
    legacyImportReferenceImages = false;
    legacyImportWardrobeItems = false;
    legacyConfirmReferencePersonaMapping = false;
    legacyConfirmMemberIds = false;
    legacyImportJournals = false;
    legacyConfirmPersonaMapping = false;
    legacyError = "";
    legacyDataError = "";
    migrationProgress = "";
    render();
    if (!migrationOnly) refresh();
  }

  function mountMigration(node) {
    mount(node, {migration: true});
  }

  function unmount() {
    generation++;
    stopQuickWorkspace();
    if (root) {
      root.removeEventListener("click", onClick);
      root.removeEventListener("change", onChange);
    }
    root = null;
    migrationOnly = false;
  }

  return {mount, mountMigration, unmount, refresh};
})();
