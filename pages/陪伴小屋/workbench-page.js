/* 统一配置工作台 · 内核
   取代此前 reply / expression / semantic / config-editor 各自实现的保存生命周期。
   各页只声明「字段 + 作用范围 + 接口」，草稿、脏状态、幂等重试、版本冲突、
   层轨与幽灵值由本文件统一负责。

   设计要点：
   - 声明式字段：kind/minimum/maximum 全部来自后端下发的 `fields` 契约，
     页面不再硬编码一份可能与校验器漂移的范围。
   - 层轨：后端下发 `layers`（继承链，外→内）与 `provenance`（每字段实际来源）。
     本文件把它画成可交互的层轨，并让悬停某层时其余层退后。
   - 幂等：保存沿用 operation_key + edit_token，结果未确认时锁编辑并只重试原请求。
   - 草稿：sessionStorage 按 installation + operator + group 隔离，切页不丢。 */
"use strict";
window.CompanionWorkbench = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2/";
  const STORE = "companion-workbench.v1:";

  /* 生效范围的四档用**自解释的长句**：四个词单独摆出来（安装/角色/关系/窗口）
     是"按实现分的类"，读的人还得先学会这套分类；写成一句话就不用解释了。
     「继承自…」那句仍用短名词，否则会读成「继承自只对这个角色生效」。 */
  const LAYER_LABELS = {
    installation: "所有角色共用", role: "只对这个角色生效",
    relationship: "只对这个人生效", window: "只在这个对话生效", scope: "生效范围",
  };
  const LAYER_SHORT_LABELS = {
    installation: "安装", role: "角色", relationship: "关系", window: "窗口",
  };
  const LAYER_ORIGINS = {
    installation: "所有角色", role: "这个角色", relationship: "这个人", window: "这个对话",
  };
  const KIND = {
    boolean: "bool", integer: "int", text: "text", probability: "float", weight: "float",
  };

  /* 取值为枚举的文本字段：注册表里它们仍是 TEXT（约束在各自领域的
     ``review_settings`` 一类校验器里），所以选项由页面声明、后端校验。
     声明缺失时退回普通文本输入，不会渲染一个空的下拉。 */
  const CHOICES = new Map();

  const errors = {
    configuration_revision_conflict: "配置已经更新。草稿已保留，读取新版本后再核对。",
    configuration_request_invalid: "请求格式有误，请刷新后重试。",
    invalid_configuration_value: "请核对数值类型与范围。",
    invalid_precision: "数值精度超出允许范围。",
    dashboard_identity_required: "请从已登录的 AstrBot 管理界面打开陪伴小屋。",
    core_access_required: "当前账号没有管理权限。",
    staging_not_initialized: "请先在账号与会话中加载 V2 运行实例。",
    staging_host_terminated: "宿主已停止，请重新进入插件。",
    bridge_timeout: "连接超时，请核对连接后重试。",
    invalid_response: "返回数据不完整，请刷新核对。",
    /* 表达学习分区（expression-page.js）走这个内核渲染，它的域内码放在这里，
       避免分区再自带一张会与内核漂移的第二份表。 */
    expression_settings_invalid: "组合不合法：单批取样条数不能小于最低样本数，候选池不能小于每轮注入规则数；也请核对各项数值范围。",
    expression_configuration_invalid: "请提供明确的配置变更。",
    expression_private_audience_required: "表达学习只适用于私聊对象。",
    expression_group_audience_required: "这一项只适用于群聊对象。",
    expression_owner_unavailable: "表达学习的工作区当前不可用，请重新选择对象。",
    expression_binding_changed: "当前角色绑定已变化，请重新选择后再操作。",
    /* 撤回 / 屏幕 / 熟人卡 / 成长四个分区也走这个内核渲染，域内码同样放在这里。 */
    recall_scope_invalid: "撤回原文转写按会话生效，请选择一个已初始化的私聊对象。",
    recall_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    recall_configuration_invalid: "请核对转写条数、字数与时间窗的取值范围。",
    screen_scope_invalid: "屏幕解读按会话生效，请选择一个已初始化的私聊对象。",
    screen_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    screen_configuration_invalid: "请核对开关与素材字数上限。",
    person_scope_invalid: "熟人卡按对象生效，请选择一个已初始化的私聊对象。",
    person_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    role_growth_scope_invalid: "成长与技能按会话生效，请选择一个已初始化的私聊对象。",
    role_growth_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    growth_target_changed: "当前对象或角色绑定已变化，请重新读取后再保存。",
    /* 知识库与日记/梦境两个分区同样走这个内核渲染。 */
    knowledge_scope_invalid: "知识库按会话生效，请选择一个已初始化的私聊对象。",
    knowledge_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    knowledge_settings_invalid: "知识库设置不合法：单轮的引用字符上限不能小于单条素材的字数上限。",
    role_life_scope_invalid: "日记与梦境按会话生效，请选择一个已初始化的私聊对象。",
    role_life_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    rest_gate_settings_invalid: "休息判定设置不合法：判定方式只能选概率或模型，时段格式形如 23:00-08:30。",
    life_timezone_invalid: "请填写有效的 IANA 时区，例如 Asia/Shanghai。",
    life_clock_invalid: "请填写二十四小时制的时刻，形如 23:50 或 00:30。",
    /* 书架与群聊参与同样经内核渲染。书架的三个码此前只写在 config-editor.js
       的导出表里，而那张表无人引用，页面因此会漏出裸机器码。 */
    library_scope_invalid: "书架按角色生效，请选择一个已初始化的私聊对象。",
    library_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    library_configuration_invalid: "请核对开关与两项数量上限的取值范围。",
    group_participation_scope_invalid: "群聊参与按会话生效，请选择一个已初始化的私聊对象。",
    group_participation_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    group_participation_configuration_invalid: "请核对群聊参与设置：概率需在 0 到 1 之间，数字项需在各自范围内；打断语只能是一行、不超过 80 字。",
    /* 参考图与衣柜（生图分区 C1）同样经内核渲染。参考图的字段校验码来自
       分组验证器（photo_reference_*），与编辑器的 reference_* 前缀不同名。 */
    reference_scope_invalid: "参考图按角色生效，请选择一个已初始化的私聊对象。",
    reference_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    reference_configuration_invalid: "请提供明确的配置变更。",
    photo_reference_configuration_invalid: "请核对两个开关与轮换天数（1 到 365）的取值范围。",
    wardrobe_scope_invalid: "衣柜按角色生效，请选择一个已初始化的私聊对象。",
    wardrobe_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    wardrobe_configuration_invalid: "请核对开关、两处文字（各不超过 800 字）与两项数量上限的取值范围。",
    /* 主动联系偏好（proactive.contact）经内核渲染。它有两层域内码：
       编辑器自己的 proactive_contact_*，以及所有者与分组校验器的 contact_* /
       invalid_contact_preference——后者是后端唯一的取值校验码，而页面能先拦的形状
       由 contactAudit 兜住，所以这里要把两张表的码都写上。 */
    proactive_contact_scope_invalid: "主动联系偏好按会话生效，请选择一个已初始化的私聊对象。",
    proactive_contact_target_changed: "当前对象或角色绑定已变化，请重新读取。",
    proactive_contact_configuration_invalid: "请核对主动联系设置：数值需在各自范围内，枚举项需在下拉选项内。",
    contact_relationship_budget_scope: "关系级配额（同一关系 24 小时内的联系与尝试上限）按安装 / 角色 / 关系层设置，不能按会话保存。",
    configuration_relationship_required: "主动联系偏好需要一个已绑定的角色和这个会话的真人关系；请先完成对象与角色的绑定。",
    invalid_contact_preference: "主动联系设置有字段不合法：时刻用 HH:MM，问候窗口用 HH:MM-HH:MM，时区用 IANA 名称，暂停时间点用带时区的 ISO 时间，活跃曲线写满 24 个数字，清单只能填允许的名字，重要日期要是 JSON 数组。",
    proactive_contact_clock_invalid: "请填写二十四小时制的时刻，形如 23:00 或 07:45。",
    proactive_contact_window_invalid: "问候窗口形如 07:45-10:20，且必须当天内结束，不能跨午夜。",
    proactive_contact_timezone_invalid: "请填写有效的 IANA 时区，例如 Asia/Shanghai。",
    proactive_contact_pause_invalid: "暂停时间点要带时区，形如 2026-09-28T12:00:00+00:00；留空表示本层不设暂停。",
    proactive_contact_curve_invalid: "活跃曲线必须写满 24 个 0.05 到 2.00 之间的数字，用逗号分隔。",
    proactive_contact_list_invalid: "清单里只能填允许的名字，用逗号分隔且不能重复；热榜来源只接受 weibo 与 hackernews。",
    proactive_contact_dates_invalid: "重要日期要写成 JSON 数组，最多 32 项。",
    proactive_contact_source_invalid: "资讯来源类型与 UID / 地址不匹配：B 站动态要十进制 UID，RSS 与 HTTPS JSON 要 https 地址。",
  };

  const e = value => String(value ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const error = (code, confirmed = false) => Object.assign(new Error(code), {code, confirmed});
  function relative(path) {
    if (typeof path !== "string" || !path.startsWith(PREFIX)) throw error("invalid_response");
    const route = path.slice(PREFIX.length);
    if (!route || /[?#%\\:]/.test(route) || route.split("/").some(part => !part || part === "." || part === "..")) {
      throw error("invalid_response");
    }
    return route;
  }
  /* 后端把机器码放在信封的 message 上（页面桥只转发 message、丢掉其余字段），
     所以取码要同时看 data.code 与 message；reason 里可能是可直接展示的原因句，
     那种情况要原样保留，不能替换成泛化文案。 */
  const isCode = value => typeof value === "string" && /^[a-z][a-z0-9_]{2,60}$/.test(value);
  const codeOf = wrapped => wrapped?.data?.code
    || (isCode(wrapped?.message) ? wrapped.message : "") || "";
  const localized = (problem, fallback) => errors[problem?.code]
    || (isCode(problem?.message) ? errors[problem.message] : problem?.message)
    || fallback;
  const icon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
  let instanceSequence = 0;

  /* === 字段契约：把后端 FieldDefinition 收敛成渲染所需的最小形状 === */
  function contract(name, definition, choices = null) {
    const kind = KIND[definition?.kind] || "text";
    return {
      name,
      kind,
      /* 枚举对文本与数字字段都生效：注册表把「有固定档位」的值注册成 INTEGER
         （如成长对日程的影响强度 0–3），只认文本会让这类字段渲染成数字框、
         丢掉档位文案。布尔字段不接受枚举——它的控件就是开关。
         缺省时保持普通输入。 */
      choices: kind !== "bool" && choices ? {...choices} : null,
      minimum: definition?.minimum ?? null,
      maximum: definition?.maximum ?? null,
      maximumChars: definition?.maximum_chars ?? null,
      decimals: definition?.decimal_places ?? (kind === "float" ? 2 : 0),
      editable: definition?.editable_layers || [],
      hasBounds: definition?.minimum != null && definition?.maximum != null,
    };
  }

  const choiceText = (item, value) => (item.choices && item.choices[value]) || value;
  const parseStringList = value => {
    try {
      const parsed = JSON.parse(String(value ?? ""));
      return Array.isArray(parsed) && parsed.every(item => typeof item === "string") ? parsed : null;
    } catch { return null; }
  };
  const parseReplacementList = value => {
    try {
      const parsed = JSON.parse(String(value ?? ""));
      if (!Array.isArray(parsed)) return null;
      const pairs = parsed.map(item => {
        if (item && typeof item === "object" && !Array.isArray(item)
            && typeof item.from === "string" && typeof item.to === "string") return {from: item.from, to: item.to};
        if (typeof item === "string" && item.includes("=>")) {
          const [from, ...rest] = item.split("=>");
          return {from: from.trim(), to: rest.join("=>").trim()};
        }
        return null;
      });
      return pairs.every(Boolean) ? pairs : null;
    } catch { return null; }
  };
  const COMPONENT_ORDER = ["voice", "at", "text", "face", "image"];
  const COMPONENT_LABELS = {voice: "语音", at: "@ 提及", text: "文字", face: "平台表情", image: "图片"};
  const visibleToken = value => value === "\n" ? "换行" : value === "\t" ? "制表符"
    : value === " " ? "空格" : value;
  const wordLabel = value => {
    const folded = value.toLocaleLowerCase();
    if (value === "\n" || folded === "<newline>") return "换行";
    if (value === "\t" || folded === "<tab>") return "制表符";
    if (value === " " || folded === "<space>") return "空格";
    return value;
  };
  const displayValue = (item, value) => item.input === "word-list"
    ? (parseStringList(value) || []).map(wordLabel).join("、") || "（空）"
    : item.input === "replacement-list"
      ? (parseReplacementList(value) || []).map(pair => `${visibleToken(pair.from)} → ${visibleToken(pair.to) || "删除"}`).join("、") || "（空）"
      : item.input === "order-list"
        ? (parseStringList(value) || []).map(kind => COMPONENT_LABELS[kind] || kind).join(" → ") || "自然顺序"
        : item.choices ? choiceText(item, value) : value;

  /* 下拉的选项键是字符串，而字段本身可能是整数；比较与写回都要先归一。 */
  const choiceKey = (item, value) => (item.choices ? String(value) : value);
  const coerceChoice = (item, value) => (item.kind === "int" ? Number(value)
    : item.kind === "float" ? Number(value) : value);

  function valid(item, value) {
    /* 快照可能带出本页面不编辑的字段（如群唤醒、风控开关）。
       那些字段没有控件、也没有契约，就不在这里判——
       它们既不会被改动，也不会进入 changes。 */
    if (!item) return true;
    if (item.kind === "bool") return typeof value === "boolean";
    if (item.input === "word-list") {
      const words = parseStringList(value);
      const policy = item.listPolicy || {};
      if (!words || words.length > (policy.maxItems || 80)
          || words.some(word => !word.length || word.length > (policy.maxLength || 200))) return false;
      if (policy.unique === "exact" && new Set(words).size !== words.length) return false;
      if (policy.unique === "casefold"
          && new Set(words.map(word => word.toLocaleLowerCase())).size !== words.length) return false;
      if (policy.numericIds && words.some(word => !/^[0-9]+$/.test(word) || word.startsWith("0"))) return false;
      return true;
    }
    if (item.input === "replacement-list") {
      const pairs = parseReplacementList(value);
      const policy = item.listPolicy || {};
      return Boolean(pairs && pairs.length <= (policy.maxItems || 80)
        && pairs.every(pair => pair.from.trim().length > 0
          && pair.from.length <= (policy.fromMaxLength || 200)
          && pair.to.length <= (policy.toMaxLength || 500)));
    }
    if (item.input === "order-list") {
      const order = parseStringList(value);
      return Boolean(order && order.length <= COMPONENT_ORDER.length
        && order.every(kind => COMPONENT_ORDER.includes(kind))
        && new Set(order).size === order.length);
    }
    /* 有档位的字段只接受档位内的值；数字字段的草稿已是数字，比较前先归一成字符串。 */
    if (item.choices) return Object.hasOwn(item.choices, String(value));
    if (item.kind === "int") {
      return Number.isInteger(value)
        && (item.minimum == null || value >= item.minimum)
        && (item.maximum == null || value <= item.maximum);
    }
    if (item.kind === "float") {
      return typeof value === "number" && Number.isFinite(value)
        && (item.minimum == null || value >= item.minimum)
        && (item.maximum == null || value <= item.maximum);
    }
    if (item.maximumChars != null && Array.from(String(value ?? "")).length > item.maximumChars) return false;
    return typeof value === "string";
  }

  /* 概率字段在界面按百分比编辑，契约里仍是 0–1 的小数。 */
  const toDisplay = (item, value) => item.kind === "float" && item.maximum === 1 && item.minimum === 0
    ? Number((value * 100).toFixed(Math.max(0, item.decimals + 2))) : value;
  const fromDisplay = (item, value) => item.kind === "float" && item.maximum === 1 && item.minimum === 0
    ? Number((value / 100).toFixed(Math.max(0, item.decimals + 2))) : value;

  /* === 渲染 === */
  function railMarkup(state, name, item, provenance, container) {
    const source = provenance?.[name]?.layer ?? null;
    const nodes = container.layers.map(layer => {
      const sourceClass = layer === source ? " is-source" : "";
      const editable = item.editable.length && !item.editable.includes(layer) ? " is-locked" : " is-editable";
      const label = LAYER_LABELS[layer] || layer;
      const shortLabel = LAYER_SHORT_LABELS[layer] || layer;
      const inherits = (!item.editable.length || item.editable.includes(layer))
        ? (layer === container.writeLayer ? "本次保存写入这一层" : `${label}层可写`)
        : `${shortLabel}层不适用于这一字段`;
      return `<span class="wb-node${sourceClass}${editable}" data-layer="${e(layer)}"`
        + ` title="${e(label)}层 · ${e(layer === source ? "当前生效值来自这里" : inherits)}"></span>`;
    }).join("");
    return `<div class="wb-rail${container.drawRails ? "" : " is-drawn"}" data-rail="${e(name)}"`
      + ` aria-hidden="true">${nodes}</div>`;
  }

  function controlMarkup(item, value, locked) {
    const dis = locked ? " disabled" : "";
    if (item.kind === "bool") {
      return `<label class="wb-switch"><input type="checkbox" data-wb-field="${e(item.name)}" ${value ? "checked" : ""}${dis}>`
        + `<span class="wb-switch-track" aria-hidden="true"></span>`
        + `<span class="wb-switch-state">${value ? "已开启" : "已关闭"}</span></label>`;
    }
    if (item.segmented) {
      const selected = choiceKey(item, value);
      const choices = Object.entries(item.choices || {}).map(([key, text]) =>
        "<label class=\"wb-segmented-option\"><input type=\"radio\" data-wb-field=\"" + e(item.name) + "\""
        + " name=\"wb-" + e(item.name) + "\" value=\"" + e(key) + "\""
        + (selected === key ? " checked" : "") + dis + "><span>" + e(text)
        + "</span></label>").join("");
      return "<div class=\"wb-segmented\" role=\"radiogroup\" aria-label=\""
        + e(item.label || item.name) + "\">" + choices + "</div>";
    }
    if (item.choices) {
      /* 枚举：空值是合法的「跟随上级」，所以不自动补一个选中项。
         草稿可能是数字（整数档位字段），选项键一定是字符串，比较前先归一。 */
      const selected = choiceKey(item, value);
      const options = Object.entries(item.choices).map(([key, text]) =>
        `<option value="${e(key)}" ${selected === key ? "selected" : ""}>${e(text)}</option>`).join("");
      return `<select data-wb-field="${e(item.name)}"${dis}>${options}</select>`;
    }
    if (item.catalog) {
      /* 选项在读取之后才知道（如 TTS 扩展目录），所以由分区声明一个
         取选项的函数；当前值不在目录里时补一条标注，避免选择被静默改写。 */
      const entries = item.catalog() || {};
      if (value !== undefined && value !== null && !Object.hasOwn(entries, value)) {
        entries[value] = `${value}（暂不可用）`;
      }
      const options = Object.entries(entries).map(([key, text]) =>
        `<option value="${e(key)}" ${value === key ? "selected" : ""}>${e(text)}</option>`).join("");
      return `<select data-wb-field="${e(item.name)}"${dis}>${options}</select>`;
    }
    if (item.kind === "text" && item.input === "word-list") {
      const words = parseStringList(value) || [];
      const policy = item.listPolicy || {};
      const limit = policy.maxItems || 80;
      const chips = words.map((word, index) =>
        "<span class=\"wb-keyword\"><span>" + e(wordLabel(word)) + "</span>"
        + "<button type=\"button\" data-wb-word-remove=\"" + e(item.name) + "\""
        + " data-wb-word-index=\"" + index + "\" aria-label=\"删除 "
        + e(wordLabel(word)) + "\" title=\"删除\">" + icon("x") + "</button></span>").join("");
      const specialLabels = {newline: "换行", space: "空格", tab: "制表符"};
      const specialWords = {newline: "\n", space: " ", tab: "\t"};
      const specials = (policy.specials || []).map(special => {
        const present = words.includes(specialWords[special]);
        const glyph = special === "newline" ? icon("corner-down-left") : "";
        return "<button type=\"button\" class=\"wb-word-special\" data-wb-word-special=\""
          + e(special) + "\" data-wb-word-field=\"" + e(item.name) + "\""
          + (locked || present || words.length >= limit ? " disabled" : "") + ">"
          + glyph + "<span>" + e(specialLabels[special] || special) + "</span></button>";
      }).join("");
      return "<div class=\"wb-word-editor\" data-wb-word-list=\"" + e(item.name) + "\">"
        + "<div class=\"wb-keywords\" role=\"group\" aria-label=\"" + e(item.label || item.name) + "\">"
        + chips + "<input class=\"wb-keyword-input\" type=\"text\" data-wb-word-input=\""
        + e(item.name) + "\" maxlength=\"" + e(policy.maxLength || 200)
        + "\" aria-label=\"添加" + e(item.label || "词条") + "\" placeholder=\"添加词条\""
        + " title=\"按 Enter 添加\"" + (locked || words.length >= limit ? " disabled" : "") + ">"
        + "<button type=\"button\" class=\"wb-keyword-add\" data-wb-word-add=\"" + e(item.name) + "\""
        + (locked || words.length >= limit ? " disabled" : "") + ">"
        + icon("plus") + "<span>添加</span></button></div>"
        + "<div class=\"wb-word-tools\">" + specials + "<span>" + words.length + " / " + limit
        + "</span></div></div>";
    }
    if (item.kind === "text" && item.input === "replacement-list") {
      const pairs = parseReplacementList(value) || [];
      const policy = item.listPolicy || {};
      const limit = policy.maxItems || 80;
      const entries = pairs.map((pair, index) =>
        "<div class=\"wb-replacement-chip\"><span>" + e(visibleToken(pair.from)) + "</span>"
        + "<span class=\"wb-replacement-arrow\" aria-hidden=\"true\">→</span><span>"
        + e(visibleToken(pair.to) || "删除") + "</span><button type=\"button\" data-wb-replacement-remove=\""
        + e(item.name) + "\" data-wb-replacement-index=\"" + index
        + "\" aria-label=\"删除替换规则\" title=\"删除\"" + dis + ">" + icon("x") + "</button></div>").join("");
      return "<div class=\"wb-replacement-editor\" data-wb-replacement-list=\"" + e(item.name) + "\">"
        + "<div class=\"wb-replacement-list\" role=\"list\" aria-label=\"" + e(item.label || item.name) + "\">"
        + entries + (pairs.length ? "" : "<span class=\"wb-empty-list\">尚未添加规则</span>") + "</div>"
        + "<div class=\"wb-replacement-form\" data-wb-replacement-form=\"" + e(item.name) + "\">"
        + "<input type=\"text\" data-wb-replacement-from=\"" + e(item.name) + "\" maxlength=\""
        + e(policy.fromMaxLength || 200) + "\" aria-label=\"匹配原词\" placeholder=\"匹配原词\"" + (locked || pairs.length >= limit ? " disabled" : "") + ">"
        + "<span class=\"wb-replacement-arrow\" aria-hidden=\"true\">→</span>"
        + "<input type=\"text\" data-wb-replacement-to=\"" + e(item.name) + "\" maxlength=\""
        + e(policy.toMaxLength || 500) + "\" aria-label=\"替换文本\" placeholder=\"替换文本（留空表示删除）\"" + (locked || pairs.length >= limit ? " disabled" : "") + ">"
        + "<button type=\"button\" class=\"wb-keyword-add\" data-wb-replacement-add=\"" + e(item.name) + "\""
        + (locked || pairs.length >= limit ? " disabled" : "") + ">" + icon("plus") + "<span>添加</span></button></div>"
        + "<div class=\"wb-word-tools\"><span>" + pairs.length + " / " + limit + " 条</span></div></div>";
    }
    if (item.kind === "text" && item.input === "order-list") {
      const order = parseStringList(value) || [];
      if (!order.length) {
        return "<div class=\"wb-order-editor\"><div class=\"wb-order-natural\">"
          + icon("shuffle") + "<span>跟随自然顺序</span></div><button type=\"button\" class=\"wb-keyword-add\""
          + " data-wb-order-start=\"" + e(item.name) + "\"" + dis + ">" + icon("list-ordered")
          + "<span>自定义顺序</span></button></div>";
      }
      const rows = order.map((kind, index) =>
        "<li class=\"wb-order-item\"><span class=\"wb-order-index\">" + (index + 1) + "</span><strong>"
        + e(COMPONENT_LABELS[kind] || kind) + "</strong><button type=\"button\" data-wb-order-move=\"up\""
        + " data-wb-order-index=\"" + index + "\" aria-label=\"上移" + e(COMPONENT_LABELS[kind] || kind)
        + "\" title=\"上移\"" + (locked || index === 0 ? " disabled" : "") + ">" + icon("chevron-up")
        + "</button><button type=\"button\" data-wb-order-move=\"down\" data-wb-order-index=\"" + index
        + "\" aria-label=\"下移" + e(COMPONENT_LABELS[kind] || kind) + "\" title=\"下移\""
        + (locked || index === order.length - 1 ? " disabled" : "") + ">" + icon("chevron-down")
        + "</button><button type=\"button\" data-wb-order-remove=\"" + e(item.name) + "\" data-wb-order-index=\""
        + index + "\" aria-label=\"移除" + e(COMPONENT_LABELS[kind] || kind) + "\" title=\"移除\""
        + dis + ">" + icon("x") + "</button></li>").join("");
      const available = COMPONENT_ORDER.filter(kind => !order.includes(kind));
      const options = available.map(kind => "<option value=\"" + e(kind) + "\">"
        + e(COMPONENT_LABELS[kind]) + "</option>").join("");
      return "<div class=\"wb-order-editor\"><ol class=\"wb-order-list\" aria-label=\"自定义发送顺序\">"
        + rows + "</ol><div class=\"wb-order-tools\"><select data-wb-order-add-select=\"" + e(item.name)
        + "\" aria-label=\"添加组件\"" + (locked || !available.length ? " disabled" : "") + ">"
        + "<option value=\"\">添加组件…</option>" + options + "</select><button type=\"button\""
        + " class=\"wb-word-special\" data-wb-order-add=\"" + e(item.name) + "\"" + (locked || !available.length ? " disabled" : "")
        + ">" + icon("plus") + "<span>添加</span></button><button type=\"button\" class=\"wb-word-special\""
        + " data-wb-order-natural=\"" + e(item.name) + "\"" + dis + ">" + icon("rotate-ccw") + "<span>恢复自然顺序</span></button></div></div>";
    }
    if (item.kind === "text") {
      /* 记忆分区的整理时刻与时区是两个「文本」字段，但 textarea 既难读也难填：
         它们其实是 time 输入与 IANA 时区名。`inputs` 声明控件类型，
         `suggestions` 给 datalist 候选项（时区名写错要到后端校验才报错）。 */
      if (item.input === "time") {
        return `<input type="time" data-wb-field="${e(item.name)}" value="${e(value)}"${dis}>`;
      }
      if (item.input === "line") {
        const list = item.suggestions ? ` list="wb-list-${e(item.name)}"` : "";
        const options = item.suggestions
          ? `<datalist id="wb-list-${e(item.name)}">${item.suggestions.map(option =>
              `<option value="${e(option)}"></option>`).join("")}</datalist>` : "";
        return `<input type="text" data-wb-field="${e(item.name)}" value="${e(value)}"${list}${dis}>${options}`;
      }
      const rows = item.rows || 3;
      const textarea = `<textarea data-wb-field="${e(item.name)}" rows="${rows}"${dis}>${e(value)}</textarea>`;
      if (item.maximumChars == null) return textarea;
      const count = Array.from(String(value ?? "")).length;
      return `<div class="wb-textarea-wrap">${textarea}<span class="wb-text-length${count > item.maximumChars ? " is-over-limit" : ""}" data-wb-counter="${e(item.name)}">${count} / ${e(item.maximumChars)} 字</span></div>`;
    }
    const shown = e(toDisplay(item, value));
    const step = item.kind === "int" ? "1" : String(1 / Math.pow(10, item.decimals));
    const bounds = item.hasBounds
      ? `<span class="wb-range">${e(item.minimum)} – ${e(item.maximum)}</span>` : "";
    const unit = item.kind === "float" && item.maximum === 1 && item.minimum === 0 ? " %" : "";
    return `<span class="wb-number"><input type="number" data-wb-field="${e(item.name)}"`
      + ` min="${e(toDisplay(item, item.minimum))}" max="${e(toDisplay(item, item.maximum))}"`
      + ` step="${e(step)}" value="${shown}"${dis}>${unit ? `<span class="wb-unit">${unit.trim()}</span>` : ""}${bounds}</span>`;
  }

  function fieldMarkup(state, container, name) {
    const item = container.fields[name];
    if (!item) return "";
    const value = state.draft[name];
    const provenance = state.status?.provenance?.[name] || {};
    const inherited = provenance.explicit === false && provenance.layer !== null;
    const locked = state.locked();
    /* 继承态：标签上显示被覆盖的幽灵值与实际生效值。 */
    let label = item.label || name;
    if (inherited) {
      const ghost = state.base?.[name];
      const shown = displayValue(item, ghost);
      const live = displayValue(item, value);
      label = `${e(item.label || name)} <span class="wb-ghost">${e(shown)}</span>`
        + `<span class="wb-live">${e(live)}</span>`;
    } else {
      label = e(item.label || name);
    }
    const chip = inherited
      ? `<span class="wb-chip">继承自${e(LAYER_ORIGINS[provenance.layer] || LAYER_LABELS[provenance.layer] || provenance.layer)}</span>` : "";
    const reset = inherited && !locked
      ? `<button type="button" class="wb-reset" data-wb-reset="${e(name)}">${icon("undo-2")}恢复继承</button>` : "";
    const dirty = state.base && value !== state.base[name] ? " is-dirty" : "";
    const inheritClass = inherited ? " is-inherited" : "";
    const visible = !item.visibleWhen || Object.entries(item.visibleWhen)
      .every(([field, expected]) => state.draft?.[field] === expected);
    return `<div class="wb-field${dirty}${inheritClass}" data-wb-row="${e(name)}"${visible ? "" : " hidden"}>`
      + railMarkup(state, name, item, state.status?.provenance, container)
      + `<div class="wb-field-main"><span class="wb-label">${label}</span>`
      + (item.help ? `<p class="wb-help">${e(item.help)}</p>` : "")
      + `<div class="wb-control">${controlMarkup(item, value, locked)}</div></div>`
      + `<div class="wb-field-side">${chip}${reset}</div></div>`;
  }

  function cardMarkup(state, container, titleAbove = "") {
    const s = state;
    /* 分区可以把自己的字段分成若干逻辑段落（如「分段」「拟人」「语音」）。
       分组只是阅读顺序，不改变作用范围：整张卡仍然共用一个编辑令牌与一次保存。 */
    const grouped = container.groups.length > 1;
    const groupMarkup = (group, index) => {
      const names = group.fields.filter(name => container.fields[name]);
      if (!names.length) return "";
      const rows = names.map(name => fieldMarkup(s, container, name)).join("");
      /* 只有一段时不必重复标题。 */
      const heading = grouped && group.title
        ? `<h4 class="wb-group-head">${e(group.title)}</h4>` : "";
      /* 段落级的依赖说明必须渲染出来。它说的是「总闸关着时下面几项为什么没反应」——
         不显示的话，用户看到一排不起作用的开关却找不到原因。数据一直传到了这里
         （spec.sections 的 help 经 group.help 进来），只是渲染时被漏掉了。
         用与字段说明同一个 .wb-help 类，保持同一套排版。 */
      const groupHelp = grouped && group.help
        ? `<p class="wb-help">${e(group.help)}</p>` : "";
      return `<section class="wb-group" data-wb-group="${e(group.id || index)}">${heading}`
        + `${groupHelp}<div class="wb-fields">${rows}</div></section>`;
    };
    const useSectionNavigation = grouped && container.groups.length <= container.navigationLimit;
    const activeGroup = container.groups.find(group => group.id === state.activeGroupId)
      || container.groups[0];
    const blocks = useSectionNavigation
      ? `<div class="wb-section-layout">
          <aside class="wb-section-sidebar">
            <div class="wb-section-nav-head"><span class="wb-section-nav-title">配置模块</span>
              <p class="wb-section-nav-note">保存会提交全部模块的改动</p></div>
            <nav class="wb-section-nav" role="tablist" aria-orientation="vertical" aria-label="${e(container.title)} 配置模块">
            ${container.groups.map((group, index) => {
              const id = group.id || String(index);
              const active = id === activeGroup?.id;
              const changed = group.fields.filter(name => s.draft?.[name] !== s.base?.[name]
                || state.resetFields.includes(name)).length;
              const count = group.fields.filter(name => container.fields[name]).length;
              return `<button type="button" class="wb-section-tab${changed ? " has-changes" : ""}"
                  id="${state.instanceId}-tab-${e(id)}" role="tab" aria-controls="${state.instanceId}-panel-${e(id)}"
                  aria-selected="${active}" tabindex="${active ? "0" : "-1"}" data-wb-section="${e(id)}">
                <span class="wb-section-index">${String(index + 1).padStart(2, "0")}</span>
                <span class="wb-section-tab-copy"><strong>${e(group.title || "配置模块")}</strong>
                  <small data-wb-section-count="${e(id)}">${changed ? `${changed} 项已改` : `${count} 项`}</small></span>
                ${icon("chevron-right")}
              </button>`;
            }).join("")}
            </nav>
          </aside>
          <div class="wb-section-panels">
            ${container.groups.map((group, index) => {
              const id = group.id || String(index);
              const active = id === activeGroup?.id;
              return `<div class="wb-section-panel" id="${state.instanceId}-panel-${e(id)}"
                  role="tabpanel" aria-labelledby="${state.instanceId}-tab-${e(id)}" tabindex="0"
                  data-wb-section-panel="${e(id)}"${active ? "" : " hidden"}>
                ${groupMarkup(group, index)}
              </div>`;
            }).join("")}
          </div>
        </div>`
      : container.groups.map(groupMarkup).join("");
    const body = s.status ? blocks
      : `<div class="wb-skeleton" role="status" aria-label="正在读取设置">`
        + `<div class="wb-skeleton-row"></div><div class="wb-skeleton-row"></div><div class="wb-skeleton-row"></div></div>`;
    const legend = s.status && container.layers.length > 1
      ? `<div class="wb-rail-legend">${container.layers.map(layer =>
          `<b>${e(LAYER_SHORT_LABELS[layer] || layer)}</b>`).join("<span>·</span>")}`
        + `</div>` : "";
    const scopeLabel = s.status
      ? (container.scopeNote || (s.status.scope === "role" ? "安装与角色"
        /* 默认写窗口、但角色层同样可写的组（技能领域、日记与作息）：值是角色共享的，
           只有本会话覆盖才落在窗口层，所以不能只标「当前会话」。
           角色层之上还有关系层的组（主动联系偏好）由分区自己声明 scopeNote：
           默认这句会说成「角色共享」，漏掉真正管着这段关系的那一层。 */
        : (s.status.layers || []).includes("role") ? "角色共享 · 本会话可覆盖" : "当前会话"))
      : "";
    const apply = s.status?.apply_mode === "next_task" ? "下一个任务生效" : "立即生效";
    return `<section class="wb-card" data-wb-card="${e(container.group)}">`
      + `<header class="wb-card-head"><div class="wb-card-copy">`
      + `${titleAbove === container.title ? "" : `<h3>${e(container.title)}</h3>`}${container.note ? `<p>${e(container.note)}</p>` : ""}</div>`
      + (scopeLabel ? `<span class="wb-scope">${e(scopeLabel)} · ${e(apply)}</span>` : "")
      + `</header><div class="wb-card-body">`
      + (s.pending ? `<div class="wb-pending"><p>上次保存结果未确认，请核对。</p>`
          + `<button type="button" class="button small" data-wb-action="retry"${s.busy ? " disabled" : ""}>核对原保存结果</button></div>` : "")
      + legend + body
      + `<div class="wb-actions">`
      + `<button type="button" class="wb-save${s.busy ? " is-busy" : ""}${s.savedState || ""}"`
      + ` data-wb-action="save"${s.locked() ? " disabled" : ""}>`
      + `<span class="wb-save-label">${e(s.busy ? "保存中" : "保存")}</span>`
      + `<svg class="wb-ring" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7"></circle></svg>`
      + `<svg class="wb-check" viewBox="0 0 19 19" aria-hidden="true"><path d="M4 10l4 4 7-9"></path></svg>`
      + `</button>`
      + `<button type="button" class="button" data-wb-action="reset"${s.locked() || !s.dirty() ? " disabled" : ""}>使用已保存配置</button>`
      + (container.resettable
        ? `<button type="button" class="button" data-wb-action="inherit"${s.locked() ? " disabled" : ""}>全部恢复继承</button>`
        : "")
      + `<span class="wb-actions-note">${e(s.dirty() ? "有未保存的改动" : "与已保存一致")}</span>`
      + `</div></div></section>`;
  }

  function noticeMarkup(state) {
    if (!state.notice) return "";
    const tone = state.bad ? " is-error" : state.ok ? " is-ok" : "";
    return `<div class="wb-notice${tone}" role="status" aria-live="polite">`
      + `${icon(state.bad ? "alert-circle" : state.ok ? "check-circle-2" : "info")}`
      + `<span>${e(state.notice)}</span></div>`;
  }

  /* === 实例 === */
  function create(spec) {
    const {
      group, title, note = "", labels = {}, helps = {}, choices = {}, sections = null,
      catalogs = {}, rows = {}, inputs = {}, suggestions = {}, segmentedChoices = [],
      visibility = {}, listFields = {}, navigationLimit = 8,
      mount: mountPoint, endpoint, order = null, pollMs = 0, query = null,
      audit = null, onStatus = null,
      /* 分组用一层继承链，但「值是谁共享的」不一定等于链上有没有角色层：
         主动联系偏好还有关系层，卡片右上角要说清这一点，所以允许分区声明自己的
         生效范围文案；不声明时仍按链自动判断。 */
      scopeNote = "",
      /* 有分区的读取键不是 `settings`、保存端点不是 `/configure`、
         令牌字段与重置字段也各有叫法。这些在 spec 里声明，不一处分叉一份内核。
         `resetKey` 默认不发送：只有真的支持恢复继承的分区才声明它，
         否则多带一个字段会被严格校验的分区直接拒掉。 */
      valuesKey = "settings", savePath = "/configure",
      tokenKey = "edit_token", sendTokenKey = null, resetKey = null,
      /* 字段名在读取侧与写入侧可以不同：记忆分区读短名 `enabled`、
         写长名 `memory.enabled`（后端 `_normalize_patch` 按 field_id 查表，
         而它自己的测试就断言长名）。声明的函数把草稿名翻成网线上的名字。 */
      outbound = null,
    } = spec;
    const wireName = outbound || (name => name);
    /* 读取侧与发送侧的令牌字段名可以不同：配置分区是 `edit_token` 收发同名，
       记忆分区读 `edit_token`、发 `expected_edit_token`。只声明一个的话，
       总有一侧拼错——读取静默落空（invalid_response），或保存被后端拒掉。 */
    const writeTokenKey = sendTokenKey || tokenKey;
    const state = {
      status: null, draft: null, base: null, pending: null,
      busy: false, loading: false, denied: false, stale: false,
      notice: "", bad: false, ok: false, savedState: "", ticket: 0,
      drawRails: true, container: null, timer: null,
      instanceId: `wb-${++instanceSequence}`, activeGroupId: null, resetFields: [],
    };
    /* 被显式「恢复继承」的字段：保存时要作为 reset_to_inherit 发出去，
       而不是留一份与继承值相同的显式副本。 */
    let resets_ = [];

    const locked = () => state.busy || state.loading || !!state.pending || !state.status || state.denied;
    const dirty = () => !!state.draft && !!state.base
      && Object.keys(state.draft).some(name => state.draft[name] !== state.base[name]);
    state.locked = locked;
    state.dirty = dirty;

    const storageKey = () => {
      const identity = window.CompanionProduct?.identity?.() || {};
      return STORE + JSON.stringify([identity.installation_id, identity.operator_id, group]);
    };
    const savePending = () => {
      try {
        if (state.pending) sessionStorage.setItem(storageKey(), JSON.stringify(state.pending));
        else sessionStorage.removeItem(storageKey());
      } catch {}
    };
    const restorePending = () => {
      try {
        const value = JSON.parse(sessionStorage.getItem(storageKey()));
        if (value && typeof value.operation_key === "string" && value.operation_key
            && typeof value.edit_token === "string" && value.edit_token.length === 64
            && value.changes && Object.keys(value.changes).length) return value;
      } catch {}
      return null;
    };

    /* 容器形状：字段顺序、契约、继承链、本次写入层 */
    function buildContainer(status) {
      const definitions = status.fields || {};
      const names = order && order.length ? order.filter(name => definitions[name])
        : Object.keys(definitions);
      const fields = {};
      for (const name of names) {
        fields[name] = contract(name, definitions[name], choices[name] || null);
        fields[name].label = labels[name] || name;
        fields[name].help = helps[name] || "";
        /* 目录型控件（选项来自读取结果，如 TTS 扩展）与多行文本框行数。 */
        if (typeof catalogs[name] === "function") fields[name].catalog = catalogs[name];
        if (rows[name]) fields[name].rows = rows[name];
        /* 控件类型：默认按 kind 决定，`inputs` 覆盖成 time / line。
           time 值仍是字符串（'23:50'），所以 kind 保持 text，只换控件。 */
       if (inputs[name]) fields[name].input = inputs[name];
       if (Array.isArray(suggestions[name])) fields[name].suggestions = suggestions[name];
        if (segmentedChoices.includes(name)) fields[name].segmented = true;
        if (visibility[name]) fields[name].visibleWhen = {...visibility[name]};
        if (listFields[name]) fields[name].listPolicy = {...listFields[name]};
      }
      /* 段落：spec.sections 声明 [{id, title, help, fields}]。
         没声明时退化成一段，标题留空——单段不强加小标题。
         段落之外的字段（若 order 里有而 sections 没提）附到最后一段，
         免得声明漏一个字段就把它从界面上弄丢。 */
      const declared = new Set();
      const groups = [];
      for (const [index, group] of (Array.isArray(sections) ? sections : []).entries()) {
        const members = (group.fields || []).filter(name => fields[name]);
        members.forEach(name => declared.add(name));
        if (members.length) {
          groups.push({id: group.id || `g${index}`, title: group.title || "", help: group.help || "",
                       fields: members});
        }
      }
      const rest = names.filter(name => !declared.has(name));
      if (rest.length) {
        if (groups.length) groups[groups.length - 1].fields.push(...rest);
        else groups.push({id: "all", title: "", help: "", fields: rest});
      }
      const layers = Array.isArray(status.layers) && status.layers.length
        ? status.layers : ["installation", "role", "window"];
      return {
        group, title, note, order: names, fields, layers, groups, scopeNote, navigationLimit,
        writeLayer: layers[layers.length - 1],
        /* 只有声明了 resetKey 的分区才提供「全部恢复继承」：
           没有这条协议的分区点了会写出错误请求。 */
        resettable: Boolean(resetKey),
        drawRails: state.drawRails,
      };
    }

    async function api(method, path, body, query) {
      let timer;
      try {
        /* 等桥注进来，别一眼看空就报「未连接」：桥的注入晚于脚本执行是正常时序。
           写法必须是 `bridgeNow() || await bridgeFor()`，不能是对 `whenBridgeReady`
           用 `??`——`??` 的右半边会立刻求值，product 没提供等待器时捕到的是
           undefined，接着 bridge?.apiGet 判空就报「没接上」，而真正该发生的
           「去等」根本没发生。 */
        const product = window.CompanionProduct;
        const bridge = product?.bridgeNow?.() || (product?.bridgeFor
          ? await product.bridgeFor() : window.AstrBotPluginPage);
        if (!bridge?.apiGet) throw error("bridge_unavailable");
        const route = relative(path);
        /* 发给桥的必须是**插件相对**路径：桥的 endpoint 不带前导斜杠、也不带插件
           目录名，宿主自己拿插件名与它拼成真实路由。这里原来发的是拼回全路径的
           `path`（`route` 算完就被丢掉），于是宿主再拼一次插件名 →
           「未找到该路由」+「Plugin bridge endpoint is invalid.」。
           同一约定见 product-page.js 的 relative() 注释。 */
        const response = await Promise.race([
          method === "GET" ? bridge.apiGet(route, query || body) : bridge.apiPost(route, body),
          new Promise((_, reject) => {timer = setTimeout(() => reject(error("bridge_timeout")), 15000);}),
        ]);
        const wrapped = ["ok", "error"].includes(response?.status) ? response
          : ["ok", "error"].includes(response?.data?.status) ? response.data : null;
        if (wrapped?.status === "error") throw error(codeOf(wrapped) || "invalid_response", true);
        const value = wrapped ? wrapped.data : response;
        if (!value || typeof value !== "object" || Array.isArray(value)) throw error("invalid_response");
        return value;
      } finally { clearTimeout(timer); }
    }

    function paint() {
      const root = mountPoint();
      if (!root) return;
      if (!state.status && !state.loading) {
        root.innerHTML = noticeMarkup(state);
        return;
      }
      if (!state.container) {
        root.innerHTML = `<div class="wb">${noticeMarkup(state)}`
          + `<p class="wb-notice">${icon("info")}<span>正在读取设置…</span></p></div>`;
        return;
      }
      const wasDrawing = state.drawRails;
      state.resetFields = resets_;
      root.innerHTML = `<div class="wb">${noticeMarkup(state)}${cardMarkup(state, state.container, root.closest?.(".console-section, .decision-stage")?.querySelector?.(":scope > header h2")?.textContent?.trim())}</div>`;
      /* 层轨绘制只做一次：重绘之后不再重播。 */
      if (wasDrawing && state.status) {
        state.drawRails = false;
        const rails = root.querySelectorAll(".wb-rail");
        rails.forEach((node, index) => {
          node.classList.add("is-drawing");
          node.style.animationDelay = `${Math.min(index, 8) * 22}ms`;
        });
        setTimeout(() => rails.forEach(node => node.classList.remove("is-drawing")), 900);
      }
      window.lucide?.createIcons({nodes: root.querySelectorAll("[data-lucide]")});
    }

    function focusSection(id) {
      const tabs = mountPoint()?.querySelectorAll?.("[data-wb-section]") || [];
      [...tabs].find(tab => tab.dataset.wbSection === id)?.focus?.({preventScroll: true});
    }

    function selectSection(id, focus = false) {
      const groups = state.container?.groups || [];
      if (!groups.some(group => group.id === id) || state.activeGroupId === id) return;
      state.activeGroupId = id;
      paint();
      if (focus) focusSection(id);
    }

    function onSectionKeydown(event) {
      const wordInput = event.target.closest?.("[data-wb-word-input]");
      if (wordInput && event.key === "Enter" && !event.isComposing) {
        event.preventDefault();
        addWord(wordInput.dataset.wbWordInput, wordInput.value);
        return;
      }
      const replacementFrom = event.target.closest?.("[data-wb-replacement-from]");
      const replacementTo = event.target.closest?.("[data-wb-replacement-to]");
      if (event.key === "Enter" && !event.isComposing && (replacementFrom || replacementTo)) {
        event.preventDefault();
        if (replacementFrom) {
          const to = replacementFrom.closest(".wb-replacement-form")?.querySelector("[data-wb-replacement-to]");
          to?.focus?.();
        } else {
          addReplacement(replacementTo.dataset.wbReplacementTo);
        }
        return;
      }
      const tab = event.target.closest?.("[data-wb-section]");
      if (!tab) return;
      const groups = state.container?.groups || [];
      const index = groups.findIndex(group => group.id === tab.dataset.wbSection);
      if (index < 0) return;
      let next = index;
      if (event.key === "ArrowDown" || event.key === "ArrowRight") next = (index + 1) % groups.length;
      else if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = (index + groups.length - 1) % groups.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = groups.length - 1;
      else return;
      event.preventDefault();
      selectSection(groups[next].id, true);
    }

    function updateSectionCounts() {
      const root = mountPoint();
      if (!root || !state.container) return;
      root.querySelectorAll("[data-wb-section-count]").forEach(node => {
        const group = state.container.groups.find(item => item.id === node.dataset.wbSectionCount);
        if (!group) return;
        const changed = group.fields.filter(name => state.draft?.[name] !== state.base?.[name]
          || resets_.includes(name)).length;
        const count = group.fields.filter(name => state.container.fields[name]).length;
        node.textContent = changed ? `${changed} 项已改` : `${count} 项`;
        node.closest("[data-wb-section]")?.classList.toggle("has-changes", changed > 0);
      });
    }

    /* 悬停：亮起该层，其余退后。用 data 属性驱动，交给 CSS。
       具名函数，这样 unmount 能真的把它们摘掉——匿名闭包摘不掉，
       宿主换绑到同一个元素上时就会越叠越多份。 */
    function onHover(event) {
      const node = event.target.closest?.(".wb-node");
      if (!node) return;
      const row = node.closest(".wb-field");
      if (!row) return;
      row.dataset.focusLayer = node.dataset.layer || "";
      row.querySelectorAll(".wb-node").forEach(item =>
        item.classList.toggle("is-focus", item === node));
    }

    function onUnhover(event) {
      const node = event.target.closest?.(".wb-node");
      if (!node) return;
      const row = node.closest(".wb-field");
      if (!row) return;
      delete row.dataset.focusLayer;
      row.querySelectorAll(".wb-node").forEach(item => item.classList.remove("is-focus"));
    }

    /* 已绑定的宿主元素。用实例级的 WeakSet 而不是元素上的 data 属性：
       data 标记在「同一个元素、内容被重写」时会把重新绑定误判成重复绑定，
       而 WeakSet 既不泄漏，也跟元素一起消失。 */
    const bound = new WeakSet();

    function bind() {
      const root = mountPoint();
      if (!root || bound.has(root)) return;
      bound.add(root);
      root.addEventListener("input", onInput);
      root.addEventListener("change", onInput);
      root.addEventListener("click", onClick);
      root.addEventListener("keydown", onSectionKeydown);
      root.addEventListener("mouseover", onHover);
      root.addEventListener("mouseout", onUnhover);
    }

    function unbind() {
      const root = mountPoint();
      if (!root || !bound.has(root)) return;
      bound.delete(root);
      root.removeEventListener("input", onInput);
      root.removeEventListener("change", onInput);
      root.removeEventListener("click", onClick);
      root.removeEventListener("keydown", onSectionKeydown);
      root.removeEventListener("mouseover", onHover);
      root.removeEventListener("mouseout", onUnhover);
    }

    function onInput(event) {
      const el = event.target;
      const name = el.dataset?.wbField;
      if (!name || !state.draft || !state.container?.fields[name]) return;
      const item = state.container.fields[name];
      const raw = item.kind === "bool" ? el.checked
        : el.tagName === "SELECT" ? coerceChoice(item, el.value)
          : item.kind === "text" ? el.value
            : fromDisplay(item, el.valueAsNumber);
      state.draft[name] = raw;
      state.savedState = "";
      state.ok = false;
      const affectsVisibility = Object.values(state.container.fields)
        .some(field => field.visibleWhen && Object.hasOwn(field.visibleWhen, name));
      if (affectsVisibility) { paint(); return; }
      /* 局部更新：不重绘整卡，避免输入框失去焦点。 */
      const row = el.closest(".wb-field");
      if (row) row.classList.toggle("is-dirty", state.base && raw !== state.base[name]);
      if (row && item.maximumChars != null) {
        const count = Array.from(String(raw ?? "")).length;
        const counter = row.querySelector("[data-wb-counter]");
        if (counter) {
          counter.textContent = `${count} / ${item.maximumChars} 字`;
          counter.classList.toggle("is-over-limit", count > item.maximumChars);
        }
        el.setAttribute("aria-invalid", String(count > item.maximumChars));
      }
      const toggle = el.closest(".wb-switch")?.querySelector(".wb-switch-state");
      if (toggle) toggle.textContent = raw ? "已开启" : "已关闭";
      const actions = mountPoint()?.querySelector(".wb-actions");
      if (actions) {
        const note = actions.querySelector(".wb-actions-note");
        if (note) note.textContent = dirty() ? "有未保存的改动" : "与已保存一致";
        const reset = actions.querySelector('[data-wb-action="reset"]');
        if (reset) reset.disabled = !dirty();
      }
      updateSectionCounts();
    }

    function onClick(event) {
      const section = event.target.closest("[data-wb-section]");
      if (section) { selectSection(section.dataset.wbSection, true); return; }
      const removeWord = event.target.closest("[data-wb-word-remove]");
      if (removeWord) {
        removeWordAt(removeWord.dataset.wbWordRemove, Number(removeWord.dataset.wbWordIndex));
        return;
      }
      const addWordButton = event.target.closest("[data-wb-word-add]");
      if (addWordButton) {
        const input = addWordButton.closest(".wb-field")?.querySelector("[data-wb-word-input]");
        if (input) addWord(addWordButton.dataset.wbWordAdd, input.value);
        return;
      }
      const specialWord = event.target.closest("[data-wb-word-special]");
      if (specialWord) {
        const value = {newline: "\n", space: " ", tab: "\t"}[specialWord.dataset.wbWordSpecial];
        if (value !== undefined) addWord(specialWord.dataset.wbWordField, value);
        return;
      }
      const addReplacementButton = event.target.closest("[data-wb-replacement-add]");
      if (addReplacementButton) { addReplacement(addReplacementButton.dataset.wbReplacementAdd); return; }
      const removeReplacementButton = event.target.closest("[data-wb-replacement-remove]");
      if (removeReplacementButton) {
        removeReplacementAt(removeReplacementButton.dataset.wbReplacementRemove,
          Number(removeReplacementButton.dataset.wbReplacementIndex));
        return;
      }
      const orderStart = event.target.closest("[data-wb-order-start]");
      if (orderStart) {
        updateOrder(orderStart.dataset.wbOrderStart, COMPONENT_ORDER, "已开启自定义组件顺序。", 0);
        return;
      }
      const orderMove = event.target.closest("[data-wb-order-move]");
      if (orderMove) {
        moveOrder(Number(orderMove.dataset.wbOrderIndex), orderMove.dataset.wbOrderMove);
        return;
      }
      const orderRemove = event.target.closest("[data-wb-order-remove]");
      if (orderRemove) {
        removeOrder(orderRemove.dataset.wbOrderRemove, Number(orderRemove.dataset.wbOrderIndex));
        return;
      }
      const orderAdd = event.target.closest("[data-wb-order-add]");
      if (orderAdd) {
        const select = orderAdd.closest(".wb-order-tools")?.querySelector("[data-wb-order-add-select]");
        addOrder(orderAdd.dataset.wbOrderAdd, select?.value);
        return;
      }
      const orderNatural = event.target.closest("[data-wb-order-natural]");
      if (orderNatural) {
        updateOrder(orderNatural.dataset.wbOrderNatural, [], "已恢复自然顺序。", null);
        return;
      }
      const reset = event.target.closest("[data-wb-reset]");
      if (reset) { revertField(reset.dataset.wbReset); return; }
      const action = event.target.closest("[data-wb-action]")?.dataset.wbAction;
      if (!action) return;
      if (action === "save") { void save(false); return; }
      if (action === "retry") { void save(true); return; }
      if (action === "reset") {
        state.draft = {...state.status.settings};
        resets_ = [];
        state.notice = "已恢复为当前已保存配置。";
        state.bad = false; state.ok = false;
        paint();
      }
      if (action === "inherit") {
        /* 全部字段恢复继承：draft 回到已保存值，并整体标记为待重置。 */
        resets_ = Object.keys(state.draft);
        state.notice = "已标记为全部恢复继承；保存后这些字段由低层配置决定。";
        state.bad = false; state.ok = false;
        paint();
      }
    }

    function addWord(name, rawWord) {
      if (!state.draft || locked()) return;
      const item = state.container?.fields[name];
      if (!item || item.input !== "word-list") return;
      const policy = item.listPolicy || {};
      const word = policy.trim ? String(rawWord ?? "").trim() : String(rawWord ?? "");
      if (!word.length) return;
      const words = parseStringList(state.draft[name]) || [];
      const duplicate = policy.unique === "casefold"
        ? words.some(value => value.toLocaleLowerCase() === word.toLocaleLowerCase())
        : words.includes(word);
      if (duplicate) {
        state.notice = "这个词条已经在列表中。";
        state.bad = false; state.ok = false; paint();
        return;
      }
      if (words.length >= (policy.maxItems || 80)) {
        state.notice = `这个列表最多添加 ${policy.maxItems || 80} 项。`;
        state.bad = true; state.ok = false; paint();
        return;
      }
      words.push(word);
      updateWordList(name, words, `已添加“${wordLabel(word)}”。`, true);
    }

    function removeWordAt(name, index) {
      if (!state.draft || locked()) return;
      const item = state.container?.fields[name];
      if (!item || item.input !== "word-list") return;
      const words = parseStringList(state.draft[name]) || [];
      if (!Number.isInteger(index) || index < 0 || index >= words.length) return;
      const [removed] = words.splice(index, 1);
      updateWordList(name, words, `已移除“${wordLabel(removed)}”。`, false);
    }

    function updateWordList(name, words, notice, focus) {
      state.draft[name] = JSON.stringify(words);
      resets_ = resets_.filter(field => field !== name);
      state.notice = notice;
      state.bad = false; state.ok = false; state.savedState = "";
      paint();
      if (focus) mountPoint()?.querySelector(`[data-wb-word-input="${name}"]`)?.focus?.();
    }

    function addReplacement(name) {
      if (!state.draft || locked()) return;
      const item = state.container?.fields[name];
      if (!item || item.input !== "replacement-list") return;
      const form = mountPoint()?.querySelector(`[data-wb-replacement-form="${name}"]`);
      const from = String(form?.querySelector("[data-wb-replacement-from]")?.value ?? "");
      const to = String(form?.querySelector("[data-wb-replacement-to]")?.value ?? "");
      const policy = item.listPolicy || {};
      if (!from.trim() || from.length > (policy.fromMaxLength || 200)
          || to.length > (policy.toMaxLength || 500)) {
        state.notice = "请填写原词，并确认替换内容没有超过长度限制。";
        state.bad = true; state.ok = false; paint();
        return;
      }
      const pairs = parseReplacementList(state.draft[name]) || [];
      if (pairs.some(pair => pair.from === from)) {
        state.notice = "这个原词已经有替换规则。";
        state.bad = false; state.ok = false; paint();
        return;
      }
      if (pairs.length >= (policy.maxItems || 80)) {
        state.notice = `这个列表最多添加 ${policy.maxItems || 80} 条规则。`;
        state.bad = true; state.ok = false; paint();
        return;
      }
      pairs.push({from, to});
      updateStructuredList(name, pairs, `已添加“${visibleToken(from)}”的替换规则。`,
        `[data-wb-replacement-from="${name}"]`);
    }

    function removeReplacementAt(name, index) {
      if (!state.draft || locked()) return;
      const item = state.container?.fields[name];
      if (!item || item.input !== "replacement-list") return;
      const pairs = parseReplacementList(state.draft[name]) || [];
      if (!Number.isInteger(index) || index < 0 || index >= pairs.length) return;
      const [removed] = pairs.splice(index, 1);
      updateStructuredList(name, pairs, `已移除“${visibleToken(removed.from)}”的替换规则。`,
        `[data-wb-replacement-from="${name}"]`);
    }

    function addOrder(name, kind) {
      const item = state.container?.fields[name];
      if (!state.draft || locked() || !item || item.input !== "order-list" || !COMPONENT_ORDER.includes(kind)) return;
      const order = parseStringList(state.draft[name]) || [];
      if (order.includes(kind)) return;
      order.push(kind);
      updateOrder(name, order, `已添加${COMPONENT_LABELS[kind]}。`, order.length - 1);
    }

    function moveOrder(index, direction) {
      const name = "component_order";
      if (!state.draft || locked()) return;
      const order = parseStringList(state.draft[name]) || [];
      const target = direction === "up" ? index - 1 : direction === "down" ? index + 1 : -1;
      if (index < 0 || target < 0 || target >= order.length) return;
      [order[index], order[target]] = [order[target], order[index]];
      updateOrder(name, order, "已调整组件顺序。", target);
    }

    function removeOrder(name, index) {
      if (!state.draft || locked()) return;
      const order = parseStringList(state.draft[name]) || [];
      if (!Number.isInteger(index) || index < 0 || index >= order.length) return;
      const [removed] = order.splice(index, 1);
      updateOrder(name, order, `已移除${COMPONENT_LABELS[removed]}。`, Math.max(0, index - 1));
    }

    function updateOrder(name, order, notice, focusIndex) {
      updateStructuredList(name, order, notice,
        focusIndex == null ? null : `[data-wb-order-move="up"][data-wb-order-index="${focusIndex}"]`);
    }

    function updateStructuredList(name, value, notice, focusSelector) {
      if (!state.draft || locked()) return;
      state.draft[name] = JSON.stringify(value);
      resets_ = resets_.filter(field => field !== name);
      state.notice = notice;
      state.bad = false; state.ok = false; state.savedState = "";
      paint();
      if (focusSelector) mountPoint()?.querySelector(focusSelector)?.focus?.();
    }

    /* 恢复继承：清掉本层的显式值，让低层重新生效。
       记进 resets_ 以便保存时发 reset_to_inherit，而不是写一份重复值。 */
    function revertField(name) {
      if (!state.status || locked()) return;
      if (!resets_.includes(name)) resets_.push(name);
      state.draft[name] = state.base[name];
      state.notice = `${labels[name] || name} 已改为恢复继承；保存后低层配置重新生效。`;
      state.bad = false; state.ok = false;
      paint();
    }

    async function refresh() {
      /* 已经有一次读取在途时不再叠加：挂载与显式刷新都会走到这里，
         而重复请求既浪费往返，也会让后到的旧快照覆盖新快照。 */
      if (state.loading) return;
      const ticket = ++state.ticket;
      state.loading = true;
      state.notice = state.status ? state.notice : "";
      paint();
      try {
        const payload = await api("GET", endpoint, null, query || undefined);
        if (ticket !== state.ticket) return;
        /* 配置接口按分区返回 {sections: {name: {...}}}；取本分区那一片。 */
        const value = payload.sections ? payload.sections[group] : payload;
        const settings = value?.[valuesKey];
        const token = value?.[tokenKey];
        if (!settings || typeof settings !== "object"
            || typeof token !== "string" || token.length !== 64) {
          throw error("invalid_response");
        }
        const nextContainer = buildContainer(value);
        /* 读取侧的令牌名可能与发送侧不同（见 writeTokenKey）。存进 status 时
           统一成 edit_token，后续只读这一个名字；发送时再翻回 writeTokenKey。 */
        if (tokenKey !== "edit_token") value.edit_token = token;
        if (valuesKey !== "settings") value.settings = settings;
        const changed = state.status && state.status.edit_token !== value.edit_token;
        state.status = value;
        state.container = nextContainer;
        if (!state.draft || changed) {
          state.draft = {...value.settings};
          state.base = {...value.settings};
          /* 后端版本变了，之前标记的「恢复继承」所依赖的基线已不成立。 */
          if (changed) resets_ = resets_.filter(name => name in state.draft);
        }
        state.stale = changed && !!state.draft;
        if (!state.pending) state.pending = restorePending();
        state.denied = false; state.bad = false;
        state.notice = state.stale
          ? "当前配置已更新，草稿仍保留；核对后可继续编辑。"
          : state.notice || "已读取当前设置。";
        state.loading = false;
        paint();
        if (onStatus) onStatus(value);
        schedule();
      } catch (problem) {
        if (ticket !== state.ticket) return;
        state.loading = false;
        state.denied = true; state.bad = true;
        state.notice = localized(problem, "暂时无法读取。请检查宿主连接后重试。");
        paint();
      }
    }

    async function save(retry) {
      if (state.busy || state.loading || state.denied) return;
      if (!retry) {
        if (state.pending) { state.notice = "先核对上次未确认的保存结果。"; paint(); return; }
        if (state.stale) { state.notice = "配置已更新，请先核对当前版本。"; paint(); return; }
        const bad = Object.entries(state.draft).find(([name, value]) =>
          !valid(state.container.fields[name], value));
        if (bad) {
          const item = state.container.fields[bad[0]];
          const count = Array.from(String(bad[1] ?? "")).length;
          state.bad = true;
          state.notice = item?.maximumChars != null && count > item.maximumChars
            ? `${item.label || bad[0]}已超过 ${item.maximumChars} 字上限。`
            : errors.invalid_configuration_value;
          paint(); return;
        }
        /* 组合约束（如「单批取样条数不能小于最低样本数」）不是单字段范围能表达的，
           由各分区自己声明。返回错误码即拦下，不发请求。 */
        const combined = audit ? audit({...state.draft}) : null;
        if (combined) {
          state.bad = true;
          state.notice = errors[combined] || "这几项的组合不合法，请调整后再保存。";
          paint();
          return;
        }
        const changes = {};
        for (const [name, value] of Object.entries(state.draft)) {
          if (value !== state.base[name]) changes[wireName(name)] = value;
        }
        /* 恢复继承：这些字段要显式告诉后端「清掉本层的值」，
           而不是写一份和继承值相同的副本。 */
        const resets = Object.keys(state.draft).filter(name =>
          resets_.includes(name) && state.draft[name] === state.base[name]).map(wireName);
        if (!Object.keys(changes).length && !resets.length) {
          state.notice = "设置没有变化。"; state.bad = false; paint(); return;
        }
        /* 存进 pending 的是**网线名**：重试要逐字节复用原请求，
           而草稿名与网线名可能不同（见 outbound）。 */
        state.pending = {
          operation_key: crypto.randomUUID(),
          edit_token: state.status.edit_token,
          changes,
          reset_to_inherit: resets,
        };
        savePending();
      }
      if (!state.pending) return;
      state.busy = true; state.bad = false; state.ok = false; state.notice = retry ? "正在核对原保存结果…" : "正在保存…";
      paint();
      const request = {...state.pending};
      try {
        const result = await api("POST", endpoint + savePath, {
          operation_key: request.operation_key,
          [writeTokenKey]: request.edit_token,
          changes: request.changes,
          ...(resetKey ? {[resetKey]: request.reset_to_inherit || []} : {}),
        });
        const receipt = result.result ?? result;
        if (typeof receipt?.operation_id !== "string" || typeof receipt?.replayed !== "boolean") {
          throw error("invalid_response");
        }
        state.pending = null; savePending();
        /* 保存确认同样按分区包裹，取本分区那一片；缺失时保留原状态。
           读取侧与发送侧的值字段名可以不同（见 valuesKey），这里也要按同一个名字回填，
           否则记忆分区保存成功后快照永远不刷新，下一次保存又会撞版本冲突。 */
        const fresh = result.status?.sections ? result.status.sections[group] : result.status;
        const freshValues = fresh && fresh[valuesKey];
        if (freshValues && typeof freshValues === "object") {
          if (valuesKey !== "settings") fresh.settings = freshValues;
          if (tokenKey !== "edit_token" && typeof fresh[tokenKey] === "string") {
            fresh.edit_token = fresh[tokenKey];
          }
          state.status = fresh;
          state.container = buildContainer(fresh);
          state.draft = {...fresh.settings};
          state.base = {...fresh.settings};
          state.stale = false;
          if (onStatus) onStatus(fresh);
        }
        state.busy = false;
        /* 幂等重放：勾画两遍，视觉上区分「新写入」与「复用旧请求确认」。 */
        state.savedState = receipt.replayed ? " is-saved is-replayed" : " is-saved";
        state.ok = true;
        state.notice = receipt.replayed
          ? "原保存已确认：这次沿用同一个操作标识，没有重复写入。"
          : "已保存。按该分区的作用范围生效。";
        paint();
        /* 有的分区不回带新快照（记忆分区的保存确认只有操作结果），
           但写入后 edit_token 已经轮换：不重新读一次，下一次保存会拿着旧令牌
           去撞版本冲突。这里补一次读取，让令牌与基线跟上。
           注意要放在 paint() 之后：refresh() 会自己重绘并给出「已读取」提示，
           先读的话保存成功的动效就看不见了。 */
        if (!freshValues) void refresh();
        setTimeout(() => {
          if (state.savedState) { state.savedState = ""; paint(); }
        }, result.result.replayed ? 1800 : 1300);
      } catch (problem) {
        state.busy = false;
        state.bad = true;
        if (problem.confirmed) {
          state.pending = null; savePending();
          state.stale = true;
          state.notice = localized(problem, "保存未通过。请读取当前设置后核对。");
        } else {
          state.notice = "保存结果尚未确认。核对时会沿用原操作标识。";
        }
        paint();
      }
    }

    function schedule() {
      stop();
      if (!pollMs || !state.status || document.hidden) return;
      state.timer = setTimeout(() => {
        if (!state.busy && !state.loading && !state.dirty()) void refresh();
        else schedule();
      }, pollMs);
    }
    function stop() { clearTimeout(state.timer); state.timer = null; }

    function mount() {
      bind();
      if (!window.CompanionProduct?.hosted?.()) {
        const root = mountPoint();
        if (root) root.innerHTML = `<p class="wb-notice">${icon("info")}`
          + `<span>请从已登录的 AstrBot 管理界面打开陪伴小屋，连接 V2 运行实例后调整这些设置。</span></p>`;
        return;
      }
      if (typeof endpoint !== "string" || !endpoint.startsWith(PREFIX)) {
        const root = mountPoint();
        if (root) root.innerHTML = `<p class="wb-notice is-error">${icon("alert-circle")}`
          + `<span>当前对象没有可用的配置工作区。请先选择已初始化的私聊对象和角色。</span></p>`;
        return;
      }
      void refresh();
    }

    /* 宿主页面每次 render() 会整块重写 innerHTML，把本工作台的 DOM 一起冲掉。
       实例仍活着（status/draft 都在），所以只需要重新绑定并重绘——
       不要再读一次：那会让「切个区域再切回来」变成一次多余往返，
       也会把页面其他地方正在用的层轨动画重播一遍。
       endpoint 变了（换了对象或角色）才需要真正重挂。 */
    function attach() {
      bind();
      paint();
    }

    function unmount() {
      state.ticket++;
      stop();
      unbind();
      state.status = null; state.container = null; state.draft = null; state.base = null;
      state.busy = false; state.loading = false; state.notice = ""; state.bad = false;
      state.ok = false; state.savedState = ""; state.drawRails = true;
      resets_ = [];
    }

    return {mount, attach, unmount, refresh, state, save, stop, start: schedule};
  }

  return {create, errors, LAYER_LABELS, contract, valid, toDisplay, fromDisplay, choiceText};
})();
