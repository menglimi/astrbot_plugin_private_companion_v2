"use strict";
window.CompanionMaintenancePage = (() => {
  const PREFIX = "/astrbot_plugin_private_companion_v2";
  const $ = (root, selector) => root.querySelector(selector);
  const fmt = (source, ...values) => source.replace(/\{\{(\d+)\}\}/g, (_, index) => String(values[index] ?? ""));
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const number = value => new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 0}).format(Number(value) || 0);
  const cost = value => "US$" + ((Number(value) || 0) / 1000000).toFixed(4);
  const percent = value => value == null ? "—" : Math.max(0, Number(value) || 0).toFixed(1) + "%";
  const localDay = value => {
    const date = value instanceof Date ? value : new Date(value || Date.now());
    if (Number.isNaN(date.getTime())) return new Date().toLocaleDateString("en-CA");
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
  };
  const time = value => {
    if (!value) return "尚无确认";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "时间未知" : new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(date);
  };
  const taskName = value => ({
    "conversation.reply": "对话回复", "proactive.compose": "主动联系",
    "proactive.judge": "主动联系复核", "memory.reflect": "记忆整理",
    "role.state.maintain": "角色状态", "calendar.plan": "日程规划",
    "role.reading.consume": "阅读理解", "role.growth.progress": "成长进展",
    "role.journal.diary": "日记", "role.journal.dream": "梦境",
    "role.journal.derive": "书写整理", "role.journal.select": "素材选择",
    "role.self_review": "自我复盘", "role.expression.learn": "表达学习",
    "content.authoring.draft": "内容起草", "conversation.context_image_caption": "图片摘要",
    "conversation.image_review": "图片审核", "screen.interpretation": "屏幕理解",
    "screen.peek": "屏幕速览", "role.state.maintenance": "状态维护",
    "role.calendar.plan": "日历规划", "memory.reflection": "记忆反思",
    "conversation.group.review": "群聊审核",
  })[value] || value || "模型任务";
  const promptTaskGroups = [
    ["对话", [["conversation.reply", "对话回复", "当前私聊的正文生成"]]],
    ["主动与记忆", [["proactive.compose", "主动联系", "有真实契机时组织联系内容"], ["proactive.judge", "主动联系复核", "复核是否符合当前人格与来源"], ["memory.reflect", "记忆整理", "从已授权素材整理认识"]]],
    ["生活与成长", [["calendar.plan", "日程规划", "基于已有目标规划下一步"], ["role.state.maintain", "角色状态", "维护角色的连续生活状态"], ["role.reading.consume", "阅读理解", "阅读实际提供的原文"], ["role.growth.progress", "成长进展", "根据已完成确认提出进展"], ["role.self_review", "自我复盘", "回看已完成的角色生活记录"], ["role.expression.learn", "表达学习", "从已授权表达样本提炼风格"]]],
    ["私人书写", [["role.journal.diary", "日记", "保存私人书写"], ["role.journal.dream", "梦境", "保存梦境记录"], ["role.journal.derive", "书写整理", "整理已有文字素材"], ["role.journal.select", "素材选择", "选择本次书写素材"]]],
    ["视觉与媒体", [["conversation.context_image_caption", "图片摘要", "从已授权图片提取可见事实"], ["conversation.image_review", "图片审核", "按合同检查图片内容"], ["screen.interpretation", "屏幕理解", "理解已授权屏幕画面"], ["screen.peek", "屏幕速览", "对已授权屏幕进行短摘要"]]],
    ["内容工作", [["content.authoring.draft", "内容起草", "根据已提供素材起草内容"]]],
  ];
  const promptTaskNames = new Map(promptTaskGroups.flatMap(([group, items]) => items.map(([kind, label, description]) => [kind, {group, label, description}])));
  const promptTaskInfo = kind => promptTaskNames.get(kind) || {group: "其他任务", label: taskName(kind), description: "V2 注册任务"};
  const stateName = value => ({
    generated: "已完成", discarded: "已收束", unknown: "结果未知",
    dispatched: "处理中", reserved: "已预留", not_started: "未发送",
  })[value] || value || "未记录";
  const flowStateName = value => ({
    collecting: "等待收口", generating: "正在生成", delivering: "正在投递",
    complete: "已完成", blocked: "已阻断", closed: "已关闭",
  })[value] || value || "状态未知";
  const flowReasonName = value => ({
    debounce: "安静窗合并", busy_delay: "忙时延后", provider_failure: "Provider 失败",
    cancelled: "已取消", owner_closed: "流程关闭", owner_unavailable: "运行端不可用",
  })[value] || value || "未记录原因";
  const failureName = value => ({
    request_preparation_failed: "请求准备失败", provider_request_failed: "Provider 请求失败",
    native_response_parse_failed: "响应解析失败", provider_recheck_failed: "Provider 状态复核失败",
    role_recheck_failed: "角色状态复核失败", response_contract_rejected: "响应未通过合同校验",
    adapter_failed: "适配器异常", provider_wait_interrupted: "Provider 等待被中断",
    request_recheck_failed: "请求状态复核失败", runtime_interrupted: "运行时中断",
  })[value] || value || "调用异常";
  const tokenSources = [
    ["companion", "陪伴插件 · 当前角色", "已连接"],
    ["memory", "记忆插件", "未接入"],
    ["together", "一起房间", "未接入"],
    ["main", "LLM 主链", "未接入"],
  ];
  const diagnosticCategories = [
    ["all", "全部", "所有运行信号"], ["model", "模型链路", "Provider、失败与未确认"],
    ["identity", "身份隔离", "管理身份与角色账本边界"],
    ["tasks", "后台任务", "任务路由与能力"], ["delivery", "消息收口", "回复片段与投递回执"],
    ["proactive", "主动触达", "已记录的主动任务"], ["image_generation", "生图", "原生图片工具注册"],
    ["image_recognition", "识图", "视觉动作注册状态"], ["voice", "语音", "TTS Provider 与合成"],
    ["storage", "SQLite", "存储连接与完整性"], ["prompt", "上下文注入", "仅来源元数据"],
    ["budget", "预算", "硬预算与后台软限额"], ["cache", "缓存", "Provider 实报与低命中样本"],
  ];
  const sourceDescriptions = {
    memory: ["记忆插件 Token", "该独立插件账本没有接入 V2 的授权统计合同。", "接入后才能显示记忆任务、Provider、最近调用与余额；当前角色数据不会替代它。"],
    together: ["一起房间 Token", "V2 当前页面无法读取该独立插件的 Token 记录。", "接入后才能显示房间任务、Provider、逐次回执与余额；不会拼入角色账本。"],
    main: ["AstrBot LLM 主链", "主链会话统计不属于 V2 角色模型调用账本。", "需要独立的宿主统计接口与会话授权；V2 不回读旧版本历史或余额。"],
  };
  const routeError = code => ({
    dashboard_identity_required: "请从已登录的 AstrBot 管理页面打开。",
    staging_not_initialized: "先在账号与会话中初始化一个运行实例。",
    model_provider_unavailable: "这个 Provider 当前没有可用的 V2 适配器。",
    model_probe_timeout: "探测超过 30 秒，结果未知。",
    model_probe_failed: "Provider 没有通过连接探测。",
    model_voice_provider_unavailable: "这个 TTS Provider 当前没有加载。",
    model_voice_probe_timeout: "合成测试超时，结果未知。",
    model_voice_probe_failed: "TTS Provider 没有完成合成测试。",
    model_storage_check_failed: "SQLite 完整性检查没有通过。",
    model_storage_check_unavailable: "SQLite 检查未完成，请稍后重试。",
    configuration_revision_conflict: "配置在其他窗口发生了变化，请先重新读取最新任务状态。",
    model_configuration_invalid: "提示词或模型配置没有通过校验，请检查长度和内容。",
    model_task_unavailable: "这个模型任务当前没有注册，无法保存提示词。",
    model_configuration_busy: "配置正在处理，请稍后重试。",
  })[code] || "检查失败，请重新读取状态后再试。";

  let root = null;
  let state = null;
  let generation = 0;

  function sourceTabsMarkup() {
    const icons = {companion: "shield-check", memory: "brain", together: "users-round", main: "workflow"};
    return tokenSources.map(([key, label, baseStatus]) => {
      const source = state.data?.external_token_sources?.[key];
      const status = key === "companion" ? baseStatus : key === "main" ? "未接入"
        : source?.available ? "已连接" : source?.installed ? "暂不可用" : "未安装";
      return fmt(
      '<button type="button" data-token-source="{{0}}" role="tab" aria-selected="{{1}}" class="{{2}}"><i data-lucide="{{3}}"></i><span>{{4}}</span><small data-state="{{5}}">{{5}}</small></button>',
      key, state.tokenSource === key, state.tokenSource === key ? "is-active" : "", icons[key], label, status);
    }).join("");
  }

  function unavailableSourceMarkup(source, summary) {
    const [title, reason, detail] = sourceDescriptions[source] || sourceDescriptions.memory;
    const pluginTitle = summary?.display_name ? summary.display_name + " Token" : title;
    const status = summary?.installed ? "插件已加载，统计桥暂不可用" : reason;
    const explanation = summary?.reason || detail;
    return '<div class="maint-source-unavailable" role="status"><div class="maint-source-glyph"><i data-lucide="plug-zap"></i></div><div class="maint-source-copy">' +
      '<span class="maint-eyebrow">SOURCE / ' + (summary?.installed ? "BRIDGE UNAVAILABLE" : "NOT CONNECTED") + '</span><strong>' + escapeHtml(pluginTitle) + '</strong><p>' + escapeHtml(status) + '</p><small>' + escapeHtml(explanation) +
      '</small><div class="maint-source-boundary"><span><i data-lucide="circle-off"></i>独立账本未混算</span><span><i data-lucide="wallet-cards"></i>服务端余额未接入</span><span><i data-lucide="shield-check"></i>V2 角色预算保持独立</span></div>' +
      '<button type="button" class="maint-source-return" data-token-source="companion"><i data-lucide="arrow-left"></i><span>返回 V2 角色账本</span></button></div></div>';
  }

  function externalBucketForPeriod(source, data) {
    const rows = Array.isArray(source.history) ? source.history : Array.isArray(source.daily) ? source.daily : [];
    const today = localDay(data.generated_at);
    if (state.period === "total") return source.totals || {};
    if (state.period === "today" || state.period === "date") {
      const day = state.period === "date" ? state.selectedDate : today;
      return rows.find(row => (row.day || row.key) === day) || {day, calls: 0, tokens: 0};
    }
    const days = state.period === "7d" ? 7 : 30;
    const start = new Date(today + "T00:00:00");
    start.setDate(start.getDate() - days + 1);
    const startDay = localDay(start);
    return aggregateUsage(rows.filter(row => {
      const day = row.day || row.key || "";
      return day >= startDay && day <= today;
    }));
  }

  function externalDimensions(source, bucket, property) {
    const rows = Array.isArray(source.history) ? source.history : [];
    if (state.period === "total") return Array.isArray(source[property]) ? source[property] : [];
    if (state.period === "today" || state.period === "date") return Array.isArray(bucket[property]) ? bucket[property] : [];
    const days = state.period === "7d" ? 7 : 30;
    const end = localDay(state.data?.generated_at);
    const start = new Date(end + "T00:00:00");
    start.setDate(start.getDate() - days + 1);
    const startDay = localDay(start);
    const totals = new Map();
    for (const day of rows.filter(row => (row.day || row.key || "") >= startDay && (row.day || row.key || "") <= end)) {
      for (const item of Array.isArray(day[property]) ? day[property] : []) {
        const key = String(item.key || "未知");
        const value = totals.get(key) || {key, calls: 0, tokens: 0, input_tokens: 0, output_tokens: 0,
          failures: 0, reported_tokens: 0, estimated_tokens: 0, cached_input_tokens: 0, cache_creation_tokens: 0,
          cache_reported_calls: 0, cache_telemetry_calls: 0, cache_input_tokens: 0, cache_other_input_tokens: 0,
          latency_total: 0, latency_samples: 0};
        for (const name of ["calls", "tokens", "input_tokens", "output_tokens", "failures", "reported_tokens", "estimated_tokens", "cached_input_tokens", "cache_creation_tokens", "cache_reported_calls", "cache_telemetry_calls", "cache_input_tokens", "cache_other_input_tokens"]) {
          value[name] += Number(item[name]) || 0;
        }
        if (item.avg_latency_ms != null) {
          value.latency_total += (Number(item.avg_latency_ms) || 0) * (Number(item.calls) || 1);
          value.latency_samples += Number(item.calls) || 1;
        }
        totals.set(key, value);
      }
    }
    return [...totals.values()].map(item => ({...item,
      avg_latency_ms: item.latency_samples ? Math.round(item.latency_total / item.latency_samples) : null,
    })).sort((a, b) => b.tokens - a.tokens).slice(0, 32);
  }

  function externalRankingMarkup(items) {
    const rows = Array.isArray(items) ? items.slice(0, 8) : [];
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>这个时间范围没有分项记录。</p></div>';
    const maximum = Math.max(1, ...rows.map(row => Number(row.tokens) || 0));
    return '<div class="maint-ranking">' + rows.map(row => {
      const width = Math.max(0, Math.min(100, Math.round((Number(row.tokens) || 0) * 100 / maximum)));
      return fmt('<div class="maint-ranking-row"><span class="maint-ranking-label">{{0}}</span><span class="maint-ranking-track"><i style="--rank-width:{{1}}%"></i></span><strong>{{2}}</strong><small>{{3}} 次</small></div>',
        escapeHtml(row.key || "未知"), width, number(row.tokens), number(row.calls));
    }).join("") + '</div>';
  }

  function cacheRateFor(row) {
    const denominator = Number(row?.cache_input_tokens) || 0;
    const reportedCalls = Number(row?.cache_reported_calls) || 0;
    return reportedCalls > 0 && denominator > 0
      ? Math.round((Number(row?.cached_input_tokens) || 0) * 1000 / denominator) / 10
      : null;
  }

  function externalDimensionTable(items, label) {
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>暂无 ' + escapeHtml(label) + ' 明细。</p></div>';
    return '<div class="maint-table-wrap"><table class="maint-table"><thead><tr><th>' + escapeHtml(label) + '</th><th>Token</th><th>调用</th><th>失败</th><th>缓存命中</th><th>已确认 / 估算</th><th>平均延迟</th></tr></thead><tbody>' +
      rows.map(row => fmt('<tr><td>{{0}}</td><td>{{1}}</td><td>{{2}}</td><td>{{3}}</td><td>{{4}}</td><td>{{5}} / {{6}}</td><td>{{7}}</td></tr>',
        escapeHtml(row.key || "未知"), number(row.tokens), number(row.calls), number(row.failures),
        cacheRateFor(row) == null ? "暂无" : percent(cacheRateFor(row)), number(row.reported_tokens), number(row.estimated_tokens),
        row.avg_latency_ms == null ? "—" : number(row.avg_latency_ms) + " ms")).join("") + '</tbody></table></div>';
  }

  function externalHistoryMarkup(rows) {
    const visible = (Array.isArray(rows) ? rows : []).slice(-30).reverse();
    if (!visible.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>该来源还没有逐日记录。</p></div>';
    return '<details class="maint-history-details"><summary>展开最近 ' + visible.length + ' 天明细</summary><div class="maint-table-wrap"><table class="maint-table"><thead><tr><th>日期</th><th>Token</th><th>已确认 / 估算</th><th>输入 / 输出</th><th>调用</th><th>失败</th></tr></thead><tbody>' +
      visible.map(row => fmt('<tr><td><button type="button" class="maint-text-action" data-select-day="{{0}}">{{0}}</button></td><td>{{1}}</td><td>{{2}} / {{3}}</td><td>{{4}} / {{5}}</td><td>{{6}}</td><td>{{7}}</td></tr>',
        escapeHtml(row.day || row.key), number(row.tokens), number(row.reported_tokens), number(row.estimated_tokens), number(row.input_tokens), number(row.output_tokens), number(row.calls), number(row.failures))).join("") +
      '</tbody></table></div></details>';
  }

  function externalRecentMarkup(rows) {
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>这个范围没有最近调用回执。</p></div>';
    return '<div class="maint-table-wrap"><table class="maint-table"><thead><tr><th>时间</th><th>任务</th><th>Provider</th><th>Token</th><th>输入 / 输出</th><th>缓存状态</th><th>已确认 / 估算</th><th>状态</th><th>耗时</th></tr></thead><tbody>' +
      rows.slice(0, 40).map(row => fmt('<tr><td>{{0}}</td><td>{{1}}</td><td>{{2}}</td><td>{{3}}</td><td>{{4}} / {{5}}</td><td>{{6}}</td><td>{{7}} / {{8}}</td><td>{{9}}</td><td>{{10}}</td></tr>',
        escapeHtml(time(row.at)), escapeHtml(row.kind), escapeHtml(row.provider), number(row.tokens), number(row.input_tokens), number(row.output_tokens),
        row.cache_hit_rate == null ? (row.cache_hit_reported ? "0%" : "暂无回执") : percent(row.cache_hit_rate),
        number(row.reported_tokens), number(row.estimated_tokens), escapeHtml(stateName(row.state)), row.latency_ms == null ? "—" : number(row.latency_ms) + " ms")).join("") +
      '</tbody></table></div>';
  }

  function externalTokenMarkup(sourceKey) {
    const source = state.data?.external_token_sources?.[sourceKey];
    if (!source?.available) return unavailableSourceMarkup(sourceKey, source);
    const data = {generated_at: state.data.generated_at, history: source.history || source.daily || [], daily: source.daily || [],
      hourly: source.hourly || [], recent: source.recent || [], windows: {}, totals: source.totals || {}};
    const row = externalBucketForPeriod(source, data);
    const rows = Array.isArray(data.history) ? data.history : [];
    const providerRows = externalDimensions(source, row, "providers");
    const taskRows = externalDimensions(source, row, "tasks");
    const day = state.period === "date" ? state.selectedDate : localDay(data.generated_at);
    const label = ({today: "今日", "7d": "近 7 日", "30d": "近 30 日", total: "累计", date: day})[state.period] || "今日";
    const stats = {tokens: Number(row.tokens) || 0};
    const compare = comparisonMarkup(usageComparison(data, stats));
    const selectedRecent = data.recent.filter(item => {
      const at = String(item.at || "").slice(0, 10);
      if (state.period === "total") return true;
      if (state.period === "date") return at === state.selectedDate;
      const days = state.period === "7d" ? 7 : state.period === "30d" ? 30 : 1;
      const start = new Date(localDay(data.generated_at) + "T00:00:00");
      start.setDate(start.getDate() - days + 1);
      return at >= localDay(start) && at <= localDay(data.generated_at);
    });
    const totalInput = Number(row.input_tokens) || 0;
    const totalCached = Number(row.cached_input_tokens) || 0;
    const cacheRate = cacheRateFor(row);
    const cacheCoverage = Number(row.calls) ? Math.round((Number(row.cache_telemetry_calls) || 0) * 1000 / Number(row.calls)) / 10 : null;
    const dailyRows = state.period === "total" ? rows : rows.slice(-30);
    const periodButtons = [["today", "今日"], ["7d", "7 日"], ["30d", "30 日"], ["total", "总计"], ["date", "按日期"]].map(item =>
      fmt('<button type="button" data-period="{{0}}" aria-pressed="{{1}}" class="{{2}}">{{3}}</button>',
        item[0], state.period === item[0], state.period === item[0] ? "is-active" : "", item[1])).join("");
    return '<div class="maint-external-source"><div class="maint-token-source-note"><i data-lucide="layers-3"></i><span>' +
      escapeHtml(source.display_name || (sourceKey === "memory" ? "记忆插件" : "一起房间")) + ' 独立账本 · 不计入 V2 角色预算 · Provider 本地价格未提供</span></div>' +
      '<div class="maint-token-controls"><div class="maint-periods" role="group" aria-label="外部 Token 统计视图">' + periodButtons +
      '</div><label class="maint-date-control"><span>查看日期</span><input type="date" data-selected-date value="' + escapeHtml(state.selectedDate || day) + '" max="' + escapeHtml(localDay(data.generated_at)) + '" ' + (state.period === "date" ? "" : "disabled") + '></label></div>' +
      '<div class="maint-token-hero maint-external-hero"><div class="maint-usage-total"><span>' + escapeHtml(label) + ' · Token 总量</span><strong>' + number(row.tokens) + '</strong><small>Token</small><div class="maint-usage-subline"><span>' + number(row.calls) + ' 次调用</span><i></i><span>费用未提供</span></div></div>' +
      '<div class="maint-external-kpis"><div><span>已确认 Token</span><strong>' + number(row.reported_tokens) + '</strong></div><div><span>估算 Token</span><strong>' + number(row.estimated_tokens) + '</strong></div><div><span>输入 / 输出</span><strong>' + number(row.input_tokens) + ' / ' + number(row.output_tokens) + '</strong></div><div><span>失败 / 平均延迟</span><strong>' + number(row.failures) + ' / ' + (row.avg_latency_ms == null ? "—" : number(row.avg_latency_ms) + " ms") + '</strong></div></div></div>' + compare +
      '<div class="maint-token-kpis maint-external-cache-kpis"><div><span>缓存命中</span><strong>' + (cacheRate == null ? "暂无回执" : number(row.cached_input_tokens)) + '</strong></div><div><span>命中率</span><strong>' + (cacheRate == null ? "暂无命中率" : percent(cacheRate)) + '</strong></div><div><span>缓存写入</span><strong>' + (Number(row.cache_telemetry_calls) ? number(row.cache_creation_tokens) : "暂无回执") + '</strong></div><div><span>回执覆盖</span><strong>' + (cacheCoverage == null ? "暂无" : percent(cacheCoverage)) + '</strong></div></div>' +
      '<div class="maint-trend-grid"><section class="maint-trend-panel"><div class="maint-subhead"><strong>逐日用量</strong><span>选择日期查看该日统计</span></div>' + chart(dailyRows) + '</section>' +
      '<section class="maint-trend-panel"><div class="maint-subhead"><strong>近 48 小时</strong><span>外部插件回执</span></div>' + recentHoursMarkup(data) + '</section></div>' +
      '<div class="maint-rank-grid"><section class="maint-rank-panel"><div class="maint-subhead"><strong>Provider 消耗排行</strong><span>' + number(providerRows.length) + ' 项</span></div>' + externalRankingMarkup(providerRows) +
      '<details class="maint-dimension-details"><summary>展开 Provider 明细</summary>' + externalDimensionTable(providerRows, "Provider") + '</details></section><section class="maint-rank-panel"><div class="maint-subhead"><strong>任务消耗排行</strong><span>' + number(taskRows.length) + ' 项</span></div>' + externalRankingMarkup(taskRows) +
      '<details class="maint-dimension-details"><summary>展开任务明细</summary>' + externalDimensionTable(taskRows, "任务") + '</details></section></div>' +
      '<section class="maint-history-panel"><div class="maint-subhead"><strong>每日明细</strong><span>最多保留一年逐日统计</span></div>' + externalHistoryMarkup(rows) + '</section>' +
      '<section class="maint-history-panel"><div class="maint-subhead"><strong>最近调用</strong><span>' + number(selectedRecent.length) + ' 条 · 来源自报状态</span></div>' + externalRecentMarkup(selectedRecent) + '</section></div>';
  }

  function sourceComparisonMarkup(data, stats) {
    const current = stats?.row || selectedBucket(data) || {};
    const sourceRows = tokenSources.map(([key, label, baseStatus]) => {
      if (key === "companion") {
        return {key, label, status: "当前角色", available: true, tokens: Number(current.tokens) || 0,
          calls: Number(current.calls) || 0, cache: stats?.cacheRate, coverage: stats?.cacheCoverage,
          scope: "计入 V2 角色预算"};
      }
      const source = data.external_token_sources?.[key];
      if (!source?.available) return {key, label, status: source?.installed ? "桥不可用" : baseStatus,
        available: false, tokens: null, calls: null, cache: null, coverage: null,
        scope: "独立账本未混算"};
      const bucket = externalBucketForPeriod(source, data) || {};
      const denominator = Number(bucket.cache_input_tokens) || 0;
      const receiptCalls = Number(bucket.cache_reported_calls) || 0;
      const telemetryCalls = Number(bucket.cache_telemetry_calls) || 0;
      return {key, label: source.display_name || label, status: "已连接", available: true,
        tokens: Number(bucket.tokens) || 0, calls: Number(bucket.calls) || 0,
        cache: receiptCalls > 0 && denominator > 0 ? Math.round((Number(bucket.cached_input_tokens) || 0) * 1000 / denominator) / 10 : null,
        coverage: Number(bucket.calls) > 0 ? Math.round(telemetryCalls * 1000 / Number(bucket.calls)) / 10 : null,
        scope: "独立账本 · 不计入 V2 预算"};
    });
    const periodLabel = ({today: "今日", "7d": "近 7 日", "30d": "近 30 日", total: "累计", date: state.selectedDate})[state.period] || "当前范围";
    const rows = sourceRows.map(row => {
      const value = row.available ? number(row.tokens) : "—";
      const calls = row.available ? number(row.calls) : "—";
      const cache = row.cache == null ? "暂无" : percent(row.cache);
      const coverage = row.coverage == null ? "暂无" : percent(row.coverage);
      return '<button type="button" class="maint-source-compare-row ' + (state.tokenSource === row.key ? "is-active" : "") + '" data-token-source="' + escapeHtml(row.key) + '" aria-pressed="' + (state.tokenSource === row.key) + '">' +
        '<span class="maint-source-compare-name"><i data-lucide="' + ({companion: "shield-check", memory: "brain", together: "users-round", main: "workflow"}[row.key] || "layers-3") + '"></i><strong>' + escapeHtml(row.label) + '</strong><small>' + escapeHtml(row.scope) + '</small></span>' +
        '<span><b>' + value + '</b><small>Token</small></span><span><b>' + calls + '</b><small>调用</small></span><span><b>' + cache + '</b><small>命中率</small></span><span><b>' + coverage + '</b><small>回执覆盖</small></span><em data-state="' + (row.available ? "ok" : "unknown") + '">' + escapeHtml(row.status) + '</em></button>';
    }).join("");
    return '<section class="maint-source-comparison" aria-label="Token 来源同周期对照"><div class="maint-subhead"><strong>来源同周期对照</strong><span>' + escapeHtml(periodLabel) + ' · 各账本独立统计</span></div><div class="maint-source-compare-head"><span>来源</span><span>Token</span><span>调用</span><span>命中率</span><span>回执覆盖</span><span>状态</span></div><div class="maint-source-compare-list">' + rows + '</div><p class="maint-source-compare-note"><i data-lucide="info"></i>对照只展示各来源已有的统计桥；未接入来源不会用 V2 当前角色数据填充。</p></section>';
  }

  function modelPath() {
    const endpoint = window.CompanionProduct?.role()?.model_api;
    if (typeof endpoint !== "string" || !endpoint.startsWith(PREFIX + "/")
        || /[?#%\\:]/.test(endpoint) || endpoint.split("/").slice(1).some(part => !part || part === "." || part === "..")) {
      throw new Error("当前对象没有模型管理接口。请先选择已初始化的会话角色。");
    }
    return endpoint.slice(PREFIX.length);
  }

  async function api(method, path, body) {
    const product = window.CompanionProduct;
    const bridge = product?.bridgeNow?.() || await product?.bridgeFor?.();
    if (!bridge) throw new Error("页面桥尚未就绪，请重新读取。");
    const response = method === "GET" ? await bridge.apiGet(path) : await bridge.apiPost(path, body || {});
    let value = response;
    for (let depth = 0; depth < 3; depth += 1) {
      if (value?.status === "error") {
        const code = value?.data?.code || value?.code || "";
        const error = new Error(routeError(code));
        error.code = code;
        throw error;
      }
      if (value?.status === "ok" && Object.hasOwn(value, "data")) {
        value = value.data;
        continue;
      }
      return value;
    }
    return value;
  }

  const PROMPT_LIMIT = 8000;
  const PROMPT_DYNAMIC_FIELDS = {
    task_input: "本次任务的结构化输入，由调用方提供。",
    role_instruction: "当前角色的角色指令，由 V2 运行端按权限提供。",
    conversation_context: "本轮会话上下文，只包含当前请求允许携带的内容。",
    recent_history: "当前任务允许使用的近期历史摘要。",
    persona_context: "当前角色的已确认人格资料。",
    image_observations: "本次请求中已授权、实际提供的图像观察结果。",
    creative_project: "当前内容创作项目及其已确认约束。",
  };

  function normalizePrompt(value) {
    return String(value ?? "").replace(/\r\n?/g, "\n");
  }

  function promptDynamicFields(prompt) {
    const fields = [];
    const seen = new Set();
    const pattern = /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g;
    let match;
    while ((match = pattern.exec(prompt))) {
      const name = match[1];
      if (seen.has(name)) continue;
      seen.add(name);
      fields.push({name, description: PROMPT_DYNAMIC_FIELDS[name] || "由 V2 调用方按当前任务合同提供的动态字段。"});
    }
    return fields;
  }

  function promptTasks() {
    const tasks = Array.isArray(state?.modelStatus?.tasks) ? state.modelStatus.tasks : [];
    return tasks.map(task => {
      const info = promptTaskInfo(task?.kind);
      const field = task?.fields?.prompt || {};
      const current = normalizePrompt(field.value);
      const inherited = normalizePrompt(field.inherited_value);
      const builtin = normalizePrompt(task?.default_prompt || inherited);
      return {...task, kind: String(task?.kind || ""), group: info.group, label: info.label,
        description: info.description, promptField: field, prompt: current, inherited,
        builtinPrompt: builtin, promptVersion: String(task?.prompt_version || "1"),
        dynamicFields: promptDynamicFields(builtin),
        customized: field.explicit === true || (current.trim() && current !== inherited)};
    }).filter(task => task.kind);
  }

  function promptSelectedTask() {
    const tasks = promptTasks();
    return tasks.find(task => task.kind === state?.promptSelectedKind) || tasks[0] || null;
  }

  function promptDirty() {
    return Boolean(state?.promptInitialized && state.promptDraft !== state.promptInitial);
  }

  function promptVisibleTasks(tasks) {
    const query = String(state.promptQuery || "").trim().toLocaleLowerCase("zh-CN");
    return tasks.filter(task => {
      if (state.promptMode === "customized" && !task.customized) return false;
      if (state.promptGroup !== "all" && task.group !== state.promptGroup) return false;
      if (!query) return true;
      return [task.label, task.kind, task.group, task.description, task.promptField?.source,
        task.promptField?.inherited_source].some(value => String(value || "").toLocaleLowerCase("zh-CN").includes(query));
    });
  }

  function reconcilePromptState() {
    const task = promptSelectedTask();
    if (!task) {
      if (state.promptInitialized && promptDirty()) {
        state.promptStale = true;
        return;
      }
      state.promptSelectedKind = "";
      state.promptDraft = "";
      state.promptInitial = "";
      state.promptEditToken = "";
      state.promptInitialized = false;
      return;
    }
    if (!state.promptInitialized || state.promptSelectedKind !== task.kind) {
      state.promptSelectedKind = task.kind;
      state.promptDraft = task.prompt;
      state.promptInitial = task.prompt;
      state.promptEditToken = String(task.edit_token || "");
      state.promptInitialized = true;
      state.promptStale = false;
      state.promptOperationKey = "";
      state.promptOperationKind = "";
      return;
    }
    const serverChanged = state.promptEditToken && task.edit_token &&
      (state.promptEditToken !== String(task.edit_token) || task.prompt !== state.promptInitial);
    if (promptDirty() && serverChanged) {
      state.promptStale = true;
      state.promptMessage = "服务器上的任务配置已变化，当前草稿仍保留；确认最新值后再决定是否覆盖。";
      state.promptMessageKind = "warn";
      return;
    }
    if (!promptDirty()) {
      state.promptDraft = task.prompt;
      state.promptInitial = task.prompt;
      state.promptEditToken = String(task.edit_token || "");
      state.promptStale = false;
    }
  }

  function promptOperationKey() {
    const task = promptSelectedTask();
    if (!task) return "";
    if (!state.promptOperationKey || state.promptOperationKind !== task.kind) {
      state.promptOperationKind = task.kind;
      state.promptOperationKey = "maintenance-prompt-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 9);
    }
    return state.promptOperationKey;
  }

  function promptGroupMarkup(tasks) {
    const groups = new Map();
    for (const task of tasks) groups.set(task.group, (groups.get(task.group) || 0) + 1);
    const ordered = promptTaskGroups.map(([group]) => group).filter(group => groups.has(group));
    for (const group of groups.keys()) if (!ordered.includes(group)) ordered.push(group);
    const allCount = state.promptMode === "customized" ? tasks.filter(task => task.customized).length : tasks.length;
    return [['all', "全部", allCount], ...ordered.map(group => [group, group,
      tasks.filter(task => task.group === group && (state.promptMode !== "customized" || task.customized)).length])]
      .map(([key, label, count]) => fmt('<button type="button" class="maint-prompt-group{{0}}" data-prompt-group="{{1}}" aria-pressed="{{2}}" {{3}}><span>{{4}}</span><b>{{5}}</b></button>',
        state.promptGroup === key ? " is-active" : "", escapeHtml(key), state.promptGroup === key,
        state.promptSaving ? "disabled" : "", escapeHtml(label), count)).join("");
  }

  function promptEditorMarkup(task) {
    if (!task) return '<div class="maint-prompt-editor-empty"><i data-lucide="list-checks"></i><strong>选择一个任务</strong><span>从左侧目录选择要调整的 V2 模型任务。</span></div>';
    const dirty = promptDirty();
    const overLimit = state.promptDraft.length > PROMPT_LIMIT;
    const message = state.promptMessage || (state.promptStale ? "配置已过期，请重新读取后再保存。" :
      dirty ? "有未保存更改" : task.customized ? "已覆盖当前任务的完整有效提示词" : "使用内置完整任务提示词");
    const messageKind = state.promptMessageKind || (state.promptStale ? "warn" : dirty ? "dirty" : "ok");
    const canSave = dirty && !state.promptSaving && !state.promptStale && !overLimit && Boolean(state.promptEditToken);
    const canReset = !state.promptSaving && !state.promptReloading && (task.customized || dirty);
    const source = task.promptField?.source || "default";
    const inheritedSource = task.promptField?.inherited_source || "default";
    const dynamicFields = task.dynamicFields.length
      ? '<div class="maint-prompt-dynamics"><div class="maint-prompt-subhead"><strong>动态字段</strong><span>由 V2 运行端注入</span></div><div class="maint-prompt-dynamic-list">' +
        task.dynamicFields.map(field => '<div><code>{{' + escapeHtml(field.name) + '}}</code><span>' + escapeHtml(field.description) + '</span></div>').join("") + '</div></div>'
      : '<div class="maint-prompt-dynamics"><div class="maint-prompt-subhead"><strong>动态字段</strong><span>当前正文未声明模板变量</span></div><p>运行时上下文仍由 V2 请求合同独立注入，本页不会展示消息正文或动态值。</p></div>';
    return '<div class="maint-prompt-editor-head"><div><span class="maint-eyebrow">' + escapeHtml(task.group) + '</span><h4>' + escapeHtml(task.label) + '</h4><p>' + escapeHtml(task.description) + '</p></div><span class="maint-prompt-badge" data-state="' + (task.customized ? "custom" : "default") + '">' + (task.customized ? "已自定义" : "内置默认") + '</span></div>' +
      '<dl class="maint-prompt-meta"><div><dt>任务键</dt><dd><code>' + escapeHtml(task.kind) + '</code></dd></div><div><dt>当前来源</dt><dd><code>' + escapeHtml(source) + '</code></dd></div><div><dt>继承来源</dt><dd><code>' + escapeHtml(inheritedSource) + '</code></dd></div><div><dt>内置版本</dt><dd><code>v' + escapeHtml(task.promptVersion) + '</code></dd></div><div><dt>版本令牌</dt><dd><code>' + (state.promptEditToken ? escapeHtml(state.promptEditToken.slice(0, 12)) + "…" : "未读取") + '</code></dd></div></dl>' +
      '<div class="maint-prompt-boundary"><i data-lucide="info"></i><span>下方只读区域是当前任务的完整内置提示词。编辑内容会替代当前任务的完整有效提示词，不会与内置正文自动拼接。</span></div>' +
      '<section class="maint-prompt-preview" aria-label="完整内置任务提示词"><div class="maint-prompt-subhead"><strong>完整内置提示词</strong><span>V2 运行端 · v' + escapeHtml(task.promptVersion) + '</span></div><pre>' + escapeHtml(task.builtinPrompt || "（内置正文未返回）") + '</pre></section>' +
      dynamicFields +
      '<label class="maint-prompt-field"><span>完整任务提示词覆盖 <small>最多 ' + PROMPT_LIMIT + ' 字</small></span><textarea data-prompt-draft rows="12" maxlength="' + PROMPT_LIMIT + '" spellcheck="false" placeholder="留空将恢复内置完整提示词。填写后会替代当前任务的完整有效提示词。">' + escapeHtml(state.promptDraft) + '</textarea></label>' +
      '<div class="maint-prompt-editor-foot"><span class="maint-prompt-status" data-state="' + escapeHtml(messageKind) + '" role="status" aria-live="polite">' + escapeHtml(message) + ' · ' + number(state.promptDraft.length) + ' / ' + PROMPT_LIMIT + ' 字</span><div class="maint-prompt-actions">' +
      (state.promptStale ? '<button type="button" class="maint-prompt-secondary" data-prompt-discard ' + (state.promptReloading ? 'disabled' : '') + '><i data-lucide="rotate-ccw"></i><span>' + (state.promptReloading ? "正在读取最新配置" : "以最新配置重载") + '</span></button>' : '') +
      '<button type="button" class="maint-prompt-secondary" data-prompt-reset ' + (canReset ? '' : 'disabled') + '><i data-lucide="rotate-ccw"></i><span>恢复默认</span></button><button type="button" class="maint-prompt-primary" data-prompt-save ' + (canSave ? '' : 'disabled') + '><i data-lucide="save"></i><span>' + (state.promptSaving ? "正在保存" : "保存提示词") + '</span></button></div></div>';
  }

  function promptWorkspaceMarkup() {
    const tasks = promptTasks();
    reconcilePromptState();
    const selected = promptSelectedTask();
    const visible = promptVisibleTasks(tasks);
    const empty = !state.modelStatus ? "正在读取模型任务目录……" : !tasks.length ? "当前没有可管理的 V2 模型任务。" : !visible.length ? "当前筛选下没有匹配的任务。" : "";
    const taskRows = visible.map(task => '<button type="button" class="maint-prompt-task' + (task.kind === state.promptSelectedKind ? ' is-active' : '') + '" data-prompt-task="' + escapeHtml(task.kind) + '" aria-pressed="' + (task.kind === state.promptSelectedKind) + '" title="' + escapeHtml(task.description) + '" ' + (state.promptSaving ? 'disabled' : '') + '><span><strong>' + escapeHtml(task.label) + '</strong><small>' + escapeHtml(task.kind) + '</small></span><i data-state="' + (task.customized ? 'custom' : 'default') + '" title="' + (task.customized ? '已自定义' : '使用内置默认') + '"></i></button>').join("");
    return '<section class="maint-prompt-section" aria-labelledby="maint-prompt-heading"><div class="maint-panel-heading"><div><span class="maint-eyebrow">PROMPTS / 01</span><h3 id="maint-prompt-heading">任务提示词</h3><p class="maint-scope-note"><i data-lucide="shield-check"></i>只管理当前角色的 V2 模型任务完整提示词，不包含 AstrBot 主对话系统提示词。</p></div><span class="maint-prompt-limit">' + tasks.length + ' 个注册任务</span></div><div class="maint-prompt-workspace"><aside class="maint-prompt-catalog" aria-label="任务提示词目录"><div class="maint-prompt-catalog-tools"><label><i data-lucide="search"></i><span class="sr-only">查找任务</span><input type="search" data-prompt-search value="' + escapeHtml(state.promptQuery) + '" placeholder="查找任务、任务键或用途" ' + (state.promptSaving ? 'disabled' : '') + '></label><div class="maint-prompt-mode" role="group" aria-label="提示词状态筛选"><button type="button" data-prompt-mode="all" aria-pressed="' + (state.promptMode === 'all') + '" class="' + (state.promptMode === 'all' ? 'is-active' : '') + '" ' + (state.promptSaving ? 'disabled' : '') + '>全部</button><button type="button" data-prompt-mode="customized" aria-pressed="' + (state.promptMode === 'customized') + '" class="' + (state.promptMode === 'customized' ? 'is-active' : '') + '" ' + (state.promptSaving ? 'disabled' : '') + '>已自定义</button></div></div><nav class="maint-prompt-groups" aria-label="任务分组">' + promptGroupMarkup(tasks) + '</nav><div class="maint-prompt-task-list" role="list">' + (empty ? '<div class="maint-prompt-list-state">' + escapeHtml(empty) + '</div>' : taskRows) + '</div></aside><section class="maint-prompt-editor" aria-label="提示词编辑器">' + promptEditorMarkup(selected) + '</section></div></section>';
  }

  function selectedDay(data) {
    return state.period === "date" ? state.selectedDate || localDay(data.generated_at) : localDay(data.generated_at);
  }

  function selectedBucket(data) {
    if (state.period === "total") return data.totals || data.summary || {};
    if (state.period === "7d" || state.period === "30d") {
      const window = data.windows?.[state.period];
      if (window?.totals) return window.totals;
      const days = Number(state.period.slice(0, -1)) || 0;
      return aggregateUsage((Array.isArray(data.daily) ? data.daily : []).slice(-days));
    }
    const day = selectedDay(data);
    const rows = Array.isArray(data.history) ? data.history : Array.isArray(data.daily) ? data.daily : [];
    return rows.find(row => row.day === day || row.key === day) || {day, calls: 0, tokens: 0};
  }

  function aggregateUsage(rows) {
    const fields = ["calls", "tokens", "cost_microusd", "unconfirmed_calls", "failures", "unknown_calls",
      "active_calls", "cache_reported_calls", "cache_telemetry_calls", "cache_input_tokens", "cached_input_tokens",
      "cache_creation_tokens", "cache_other_input_tokens", "input_tokens", "output_tokens", "reported_tokens", "estimated_tokens"];
    const result = Object.fromEntries(fields.map(name => [name, 0]));
    let latencyWeighted = 0;
    let latencySamples = 0;
    for (const row of rows) {
      for (const name of fields) result[name] += Number(row[name]) || 0;
      const samples = Number(row.latency_samples) || (row.avg_latency_ms == null ? 0 : Number(row.calls) || 0);
      latencyWeighted += (Number(row.avg_latency_ms) || 0) * samples;
      latencySamples += samples;
    }
    result.avg_latency_ms = latencySamples ? Math.round(latencyWeighted / latencySamples) : null;
    return result;
  }

  function statsFor(data) {
    const row = selectedBucket(data);
    const calls = Number(row.calls) || 0;
    const unconfirmed = Number(row.unconfirmed_calls) || 0;
    const knownCalls = Math.max(0, calls - unconfirmed);
    const cacheCalls = Number(row.cache_reported_calls) || 0;
    const cacheInput = Number(row.cache_input_tokens) || 0;
    const cached = Number(row.cached_input_tokens) || 0;
    return {
      row, day: selectedDay(data), calls, tokens: Number(row.tokens) || 0,
      cost: Number(row.cost_microusd) || 0, failures: Number(row.failures) || 0,
      unconfirmed, unknown: Number(row.unknown_calls) || 0, active: Number(row.active_calls) || 0,
      cacheCalls, cacheTelemetryCalls: Number(row.cache_telemetry_calls) || 0,
      cacheInput, cached, creation: Number(row.cache_creation_tokens) || 0,
      other: Number(row.cache_other_input_tokens) || 0, input: Number(row.input_tokens) || 0,
      output: Number(row.output_tokens) || 0, latency: row.avg_latency_ms,
      cacheRate: cacheCalls > 0 && cacheInput ? Math.round(cached * 1000 / cacheInput) / 10 : null,
      cacheCoverage: knownCalls ? Math.round(cacheCalls * 1000 / knownCalls) / 10 : null,
    };
  }

  function usageComparison(data, stats) {
    if (state.period === "total") return null;
    const days = state.period === "30d" ? 30 : state.period === "7d" ? 7 : 1;
    const end = state.period === "date" ? stats.day : localDay(data.generated_at);
    const startDate = new Date(end + "T00:00:00");
    startDate.setDate(startDate.getDate() - days + 1);
    const currentStart = localDay(startDate);
    startDate.setDate(startDate.getDate() - days);
    const previousStart = localDay(startDate);
    const previousEndDate = new Date(currentStart + "T00:00:00");
    previousEndDate.setDate(previousEndDate.getDate() - 1);
    const previousEnd = localDay(previousEndDate);
    const history = Array.isArray(data.history) ? data.history : Array.isArray(data.daily) ? data.daily : [];
    const previousRows = history.filter(row => {
      const day = row.day || row.key || "";
      return day >= previousStart && day <= previousEnd;
    });
    if (!previousRows.length) return {label: days === 1 ? "较前一日" : "较前 " + days + " 日", empty: true};
    const previous = aggregateUsage(previousRows);
    const delta = stats.tokens - previous.tokens;
    const rate = previous.tokens ? delta * 100 / previous.tokens : null;
    return {label: days === 1 ? "较前一日" : "较前 " + days + " 日", previous: previous.tokens, delta, rate};
  }

  function comparisonMarkup(comparison) {
    if (!comparison) return "";
    if (comparison.empty) return '<div class="maint-period-comparison" data-state="unknown"><span>周期对比</span><strong>前期暂无记录</strong><small>' + escapeHtml(comparison.label) + '</small></div>';
    const tone = comparison.delta > 0 ? "up" : comparison.delta < 0 ? "down" : "flat";
    const change = comparison.rate == null
      ? comparison.delta > 0 ? "新增 " + number(comparison.delta) + " Token" : comparison.delta < 0 ? "减少 " + number(Math.abs(comparison.delta)) + " Token" : "持平"
      : (comparison.delta > 0 ? "+" : "") + comparison.rate.toFixed(1) + "%";
    return '<div class="maint-period-comparison" data-state="' + tone + '"><span>周期对比</span><strong>' + escapeHtml(change) + '</strong><small>' + escapeHtml(comparison.label) + ' · 前期 ' + number(comparison.previous) + ' Token</small></div>';
  }

  function chart(rows) {
    const visible = (Array.isArray(rows) ? rows : []).slice(-30);
    const maximum = Math.max(1, ...visible.map(row => Number(row.tokens) || 0));
    return '<div class="maint-chart" data-count="' + visible.length + '" style="--day-count:' + Math.max(1, visible.length) + '" aria-label="最近 30 日 Token 趋势">' +
      visible.map(row => {
        const tokens = Number(row.tokens) || 0;
        const day = row.day || row.key || "";
        const height = tokens ? Math.max(4, Math.round(tokens / maximum * 74)) : 2;
        const parsed = new Date(day + "T00:00:00");
        const label = Number.isNaN(parsed.getTime()) ? day : new Intl.DateTimeFormat("zh-CN", {month: "numeric", day: "numeric"}).format(parsed);
        const selected = state.period === "date" && state.selectedDate === day;
        return fmt('<button class="maint-chart-day" type="button" data-select-day="{{0}}" aria-pressed="{{6}}" aria-label="选择 {{1}}，{{2}} Token，{{3}} 次调用" title="{{1}} · {{2}} Token · {{3}} 次调用"><span class="maint-chart-column" style="--bar-height:{{4}}px"></span><small>{{5}}</small></button>',
          escapeHtml(day), escapeHtml(day), number(tokens), number(row.calls), height, escapeHtml(label), selected);
      }).join("") + "</div>";
  }

  function hourlyMarkup(data, stats) {
    const rows = (Array.isArray(data.hourly) ? data.hourly : []).filter(row => row.day === stats.day);
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">24</span><p>这一天还没有小时级调用记录。</p></div>';
    const byHour = new Map(rows.map(row => [String(row.hour).padStart(2, "0"), row]));
    const values = Array.from({length: 24}, (_, hour) => {
      const key = String(hour).padStart(2, "0");
      return {hour: key, ...(byHour.get(key) || {tokens: 0, calls: 0})};
    });
    const maximum = Math.max(1, ...values.map(row => Number(row.tokens) || 0));
    return '<div class="maint-hour-chart" aria-label="' + escapeHtml(stats.day) + ' 每小时 Token 趋势">' + values.map(row => {
      const height = Number(row.tokens) ? Math.max(4, Math.round(row.tokens / maximum * 56)) : 2;
      return fmt('<div class="maint-hour-bar" title="{{0}}:00 · {{1}} Token · {{2}} 次"><span style="--bar-height:{{3}}px"></span><small>{{4}}</small></div>',
        row.hour, number(row.tokens), number(row.calls), height, Number(row.hour) % 3 === 0 ? row.hour : "");
    }).join("") + "</div>";
  }

  function recentHoursMarkup(data) {
    const rows = Array.isArray(data.hourly) ? data.hourly : [];
    const byHour = new Map(rows.map(row => [String(row.day || "") + "T" + String(row.hour).padStart(2, "0"), row]));
    const stamp = String(data.generated_at || new Date().toISOString()).slice(0, 13);
    const anchor = new Date(stamp + ":00:00Z");
    if (Number.isNaN(anchor.getTime())) return '<div class="maint-empty"><span class="maint-empty-mark">48</span><p>暂时无法确定小时趋势范围。</p></div>';
    const values = Array.from({length: 48}, (_, index) => {
      const date = new Date(anchor.getTime() - (47 - index) * 3600000);
      const key = date.toISOString().slice(0, 13);
      return {key, day: key.slice(0, 10), hour: key.slice(11, 13), ...(byHour.get(key) || {tokens: 0, calls: 0})};
    });
    const maximum = Math.max(1, ...values.map(row => Number(row.tokens) || 0));
    return '<div class="maint-hour-chart-wrap"><div class="maint-hour-chart maint-hour-chart-48" aria-label="最近 48 小时 Token 趋势">' +
      values.map((row, index) => {
        const height = Number(row.tokens) ? Math.max(3, Math.round(row.tokens / maximum * 56)) : 2;
        const label = index % 6 === 0 || index === 47 ? row.hour : "";
      const selected = state.selectedHour === row.key;
      return fmt('<button class="maint-hour-bar{{7}}" type="button" data-select-hour="{{0}}" data-select-day="{{1}}" aria-pressed="{{8}}" aria-label="聚焦 {{2}}，{{3}} Token，{{4}} 次调用" title="{{2}} · {{3}} Token · {{4}} 次调用"><span style="--bar-height:{{5}}px"></span><small>{{6}}</small></button>',
        escapeHtml(row.key), escapeHtml(row.day), escapeHtml(row.key.replace("T", " ") + ":00"), number(row.tokens), number(row.calls), height, label,
        selected ? " is-selected" : "", selected);
      }).join("") + "</div></div>";
  }

  function trendHourlyMarkup(data, stats) {
    if (state.period === "date") return hourlyMarkup(data, stats);
    return recentHoursMarkup(data);
  }

  function dimensions(data, stats, key) {
    if (state.period === "total") return Array.isArray(stats.row[key]) ? stats.row[key] : [];
    if ((state.period === "7d" || state.period === "30d") && Array.isArray(data.windows?.[state.period]?.[key])) {
      return data.windows[state.period][key];
    }
    return Array.isArray(stats.row[key]) ? stats.row[key] : [];
  }

  function rankingMarkup(items, kind) {
    const rows = Array.isArray(items) ? items.slice(0, 8) : [];
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>当前统计范围暂无明细。</p></div>';
    const maximum = Math.max(1, ...rows.map(row => Number(row.tokens) || 0));
    return '<div class="maint-ranking">' + rows.map(row => {
      const key = row.key || "未知";
      const label = kind === "tasks" ? taskName(key) : key;
      const width = Math.max(0, Math.min(100, Math.round((Number(row.tokens) || 0) * 100 / maximum)));
      return fmt('<button type="button" class="maint-ranking-row" data-rank-kind="{{0}}" data-rank-key="{{1}}" title="筛选最近调用：{{2}}"><span class="maint-ranking-label">{{2}}</span><span class="maint-ranking-track"><i style="--rank-width:{{3}}%"></i></span><strong>{{4}}</strong><small>{{5}} 次</small></button>',
        kind, escapeHtml(key), escapeHtml(label), width, number(row.tokens), number(row.calls));
    }).join("") + "</div>";
  }

  function detailTable(items, kind) {
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>暂无可展开的明细。</p></div>';
    return '<div class="maint-table-wrap"><table class="maint-table"><thead><tr><th>' +
      (kind === "providers" ? "Provider" : "任务") +
      '</th><th>Token</th><th>调用</th><th>失败</th><th>缓存命中</th><th>平均延迟</th><th>本地计价</th></tr></thead><tbody>' +
      rows.map(row => fmt('<tr><td>{{0}}</td><td>{{1}}</td><td>{{2}}</td><td>{{3}}</td><td>{{4}}</td><td>{{5}}</td><td>{{6}}</td></tr>',
        escapeHtml(kind === "tasks" ? taskName(row.key) : row.key || "未知 Provider"),
        number(row.tokens), number(row.calls), number(row.failures),
        percent(Number(row.cache_input_tokens) ? Number(row.cached_input_tokens) * 100 / Number(row.cache_input_tokens) : null),
        row.avg_latency_ms == null ? "—" : number(row.avg_latency_ms) + " ms", cost(row.cost_microusd))).join("") +
      '</tbody></table></div>';
  }

  function historyMarkup(data) {
    const rows = (Array.isArray(data.history) ? data.history : Array.isArray(data.daily) ? data.daily : []).slice(-30).reverse();
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>尚无历史用量。</p></div>';
    return '<details class="maint-history-details"><summary>展开最近 ' + rows.length + ' 天明细</summary><div class="maint-table-wrap"><table class="maint-table"><thead><tr><th>日期</th><th>Token</th><th>输入 / 输出</th><th>调用</th><th>失败</th><th>本地计价</th></tr></thead><tbody>' +
      rows.map(row => fmt('<tr><td><button type="button" class="maint-text-action" data-select-day="{{0}}">{{0}}</button></td><td>{{1}}</td><td>{{2}} / {{3}}</td><td>{{4}}</td><td>{{5}}</td><td>{{6}}</td></tr>',
        escapeHtml(row.day || row.key), number(row.tokens), number(row.input_tokens), number(row.output_tokens),
        number(row.calls), number(row.failures), cost(row.cost_microusd))).join("") +
      '</tbody></table></div></details>';
  }

  function recentRows(data) {
    const rows = Array.isArray(data.recent) ? data.recent : [];
    if (state.period === "total") return rows;
    if (state.period === "date") return rows.filter(row => String(row.at || "").slice(0, 10) === selectedDay(data));
    const today = localDay(data.generated_at);
    const days = state.period === "7d" ? 7 : state.period === "30d" ? 30 : 1;
    const start = new Date(today + "T00:00:00");
    start.setDate(start.getDate() - days + 1);
    const startDay = localDay(start);
    return rows.filter(row => {
      const day = String(row.at || "").slice(0, 10);
      return day >= startDay && day <= today;
    });
  }

  function matchingRecent(data) {
    let rows = recentRows(data);
    if (state.traceFilter?.kind === "providers") rows = rows.filter(row => row.provider === state.traceFilter.key);
    if (state.traceFilter?.kind === "tasks") rows = rows.filter(row => row.kind === state.traceFilter.key);
    if (state.callFilter === "failed") rows = rows.filter(row => row.failure);
    if (state.callFilter === "uncertain") rows = rows.filter(row => row.state === "unknown" || row.tokens == null);
    if (state.callFilter === "cache-low") rows = rows.filter(row => row.cache_hit_rate != null && Number(row.input_tokens) >= 1000 && Number(row.cache_hit_rate) < 20);
    if (state.callQuery) {
      const query = state.callQuery.trim().toLocaleLowerCase();
      rows = rows.filter(row => (String(row.provider || "") + " " + taskName(row.kind) + " " + failureName(row.failure) + " " + String(row.failure || "") + " " + String(row.at || ""))
        .toLocaleLowerCase().includes(query));
    }
    if (state.selectedHour) rows = rows.filter(row => String(row.at || "").slice(0, 13) === state.selectedHour);
    return rows;
  }

  function filteredRecent(data) {
    return matchingRecent(data).slice(0, state.showAllCalls ? 80 : 10);
  }

  function recentMarkup(data) {
    const rows = filteredRecent(data);
    if (!rows.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>当前筛选范围没有调用记录。</p></div>';
    return '<div class="maint-call-list">' + rows.map((row, index) => {
      const tokens = row.tokens == null ? "用量未知" : number(row.tokens) + " Token";
      const cache = row.cached_input_tokens != null && row.input_tokens != null
        ? "缓存命中 " + number(row.cached_input_tokens) + " · " + (row.cache_hit_rate == null ? "无可计算比例" : row.cache_hit_rate + "%")
        : row.cache_creation_tokens != null ? "缓存写入 " + number(row.cache_creation_tokens) + " · 命中字段不完整" : "Provider 未报告缓存用量";
      const failure = row.failure ? '<span class="maint-call-failure">' + escapeHtml(failureName(row.failure)) + "</span>" : "";
      return fmt('<details class="maint-call-row" {{0}}><summary><span class="maint-call-time">{{1}}</span><span class="maint-call-task">{{2}}</span><span class="maint-call-provider">{{3}}</span><span class="maint-call-total">{{4}}</span><span class="maint-call-state" data-state="{{5}}">{{6}}</span></summary><div class="maint-call-detail"><span>输入 {{7}} · 输出 {{8}}</span><span>{{9}}</span><span>{{10}} 本地计价</span><span>{{11}}</span>{{12}}</div></details>',
        index === 0 ? "open" : "", escapeHtml(time(row.at)), escapeHtml(taskName(row.kind)),
        escapeHtml(row.provider || "未知 Provider"), escapeHtml(tokens), escapeHtml(row.state), escapeHtml(stateName(row.state)),
        number(row.input_tokens), number(row.output_tokens), escapeHtml(cache), cost(row.cost_microusd),
        row.latency_ms == null ? "耗时未记录" : number(row.latency_ms) + " ms", failure);
    }).join("") + "</div>";
  }

  function diagnosticItems(data, stats) {
    const items = [];
    const add = (severity, category, title, detail, action) => items.push({severity, category, title, detail, action: action || ""});
    if (stats.failures) add("error", "model", "模型调用出现失败", number(stats.failures) + " 次失败 · 可从事件线定位任务与 Provider。", "failed");
    if (stats.active) add("warn", "model", "存在未收束的模型调用", number(stats.active) + " 条记录仍处于预留或处理中状态。", "uncertain");
    if (stats.unconfirmed || stats.unknown) add("warn", "model", "部分调用还没有确认结果",
      number(stats.unconfirmed) + " 条用量未确认 · " + number(stats.unknown) + " 条结果未知；未知结果不会自动重放。", "uncertain");
    if (!(data.providers || []).length) add("warn", "model", "没有已加载的 V2 文本 Provider", "模型任务目前无法通过 V2 适配器执行。", "provider");
    const modelStatus = state.modelStatus;
    const identityScope = data.runtime?.identity_scope || {};
    if (identityScope.dashboard_operator !== "verified" || identityScope.role_access !== "verified"
        || identityScope.token_ledger !== "current_role") {
      add("error", "identity", "身份或账本边界尚未确认", "本次管理请求缺少完整的身份与当前角色范围回执。", "identity");
    }
    if (modelStatus && Array.isArray(modelStatus.tasks)) {
      const providers = Array.isArray(modelStatus.providers) ? modelStatus.providers : [];
      const byId = new Map(providers.map(item => [item.id, item]));
      for (const task of modelStatus.tasks) {
        const primary = task.fields?.provider?.value || "";
        const fallback = task.fields?.fallback?.value || "";
        const required = Array.isArray(task.capabilities) ? task.capabilities : [];
        const primaryModel = byId.get(primary);
        const title = taskName(task.kind) + "路由";
        if (!primary) add("warn", task.kind === "conversation.reply" ? "model" : "tasks", title + "没有主 Provider", "请检查下方模型任务配置中的主路由。", "route");
        else if (!primaryModel) add("warn", task.kind === "conversation.reply" ? "model" : "tasks", title + "的 Provider 不可用", primary + " 未出现在当前 V2 模型路由中。", "route");
        else if (!required.every(capability => (primaryModel.capabilities || []).includes(capability))) {
          add("error", task.kind === "conversation.reply" ? "model" : "tasks", title + "能力不匹配", primary + " 缺少此任务要求的能力。", "route");
        }
        const outputLimit = Number(task.fields?.max_output_tokens?.value) || 0;
        if (primaryModel && outputLimit > Number(primaryModel.max_output_tokens || 0)) {
          add("error", task.kind === "conversation.reply" ? "model" : "tasks", title + "输出上限过高",
            number(outputLimit) + " 超过 Provider 可用上限 " + number(primaryModel.max_output_tokens) + "。", "route");
        }
        if (fallback && !byId.has(fallback)) add("warn", task.kind === "conversation.reply" ? "model" : "tasks", title + "的备用 Provider 不可用", fallback + " 未出现在当前 V2 模型路由中。", "route");
      }
    }
    const limit = Number(data.budget?.limit_tokens) || 0;
    const used = (Number(data.budget?.spent_tokens) || 0) + (Number(data.budget?.held_tokens) || 0);
    if (limit && used / limit >= .9) add("warn", "budget", "今日硬预算接近上限", number(used) + " / " + number(limit) + " Token。", "budget");
    else if (data.budget?.soft_limit_enabled && Number(data.budget?.soft_limit_tokens) > 0 && used >= Number(data.budget.soft_limit_tokens)) {
      add("info", "budget", "后台任务软限额已触发", "部分可延后任务可能暂缓。", "budget");
    }
    if (stats.cacheCalls && stats.cacheRate != null && stats.cacheRate < 20) {
      add("warn", "cache", "缓存命中偏低", "有效命中率 " + percent(stats.cacheRate) + "；稳定前缀与动态上下文可作为排查方向。", "cache-low");
    }
    if (stats.knownCalls && stats.cacheCoverage != null && stats.cacheCoverage < 50) {
      add("info", "cache", "缓存确认覆盖有限", number(stats.cacheCalls) + " / " + number(stats.knownCalls) + " 次已确认调用提供可计算命中字段。", "cache");
    }
    const runtime = data.runtime || {};
    const storage = runtime.storage || {};
    if (storage.journal_mode && storage.journal_mode !== "wal") {
      add("warn", "storage", "SQLite 未使用 WAL", "当前连接模式为 " + storage.journal_mode.toUpperCase() + "；可运行完整性检查核对数据库状态。", "storage");
    }
    if (storage.foreign_keys === false) add("error", "storage", "SQLite 外键保护未启用", "当前存储连接没有启用外键约束。", "storage");
    const flows = Array.isArray(runtime.conversation) ? runtime.conversation : [];
    const failedParts = flows.reduce((sum, row) => sum + (Number(row.failed_parts) || 0), 0);
    const uncertainParts = flows.reduce((sum, row) => sum + (Number(row.unknown_parts) || 0), 0);
    const pendingParts = flows.reduce((sum, row) => sum + (Number(row.pending_parts) || 0), 0);
    if (failedParts) add("error", "delivery", "回复消息投递失败", number(failedParts) + " 个片段收到失败回执；可检查最近收口轨迹。", "delivery");
    if (uncertainParts) add("warn", "delivery", "回复投递结果未知", number(uncertainParts) + " 个片段没有确定回执；未知结果不会自动重发。", "delivery");
    if (pendingParts) add("info", "delivery", "回复仍在等待投递", number(pendingParts) + " 个片段处于待发送或发送中状态。", "delivery");
    const voice = state.integrations?.voice;
    const image = state.integrations?.image;
    if (!voice) add("info", "voice", "TTS 状态未能读取", "重新同步后可检查独立的语音 Provider。", "voice");
    else if (!(voice.providers || []).length) add("info", "voice", "没有已加载的 TTS Provider", "语音合成测试暂不可用。", "voice");
    if (!image) add("info", "image_generation", "图片扩展状态未能读取", "可重新同步原生图片工具注册状态。", "image");
    else {
      const actions = Array.isArray(image.actions) ? image.actions : [];
      if (!actions.some(row => row.action === "generate" && row.registered && row.current)) {
        add("warn", "image_generation", "没有当前注册的生图工具", "这里仅验证工具注册；不会提交真实生成请求。", "image");
      }
      if (!actions.some(row => row.action === "recognize" && row.registered && row.current)) {
        add("info", "image_recognition", "没有当前注册的识图工具", "检查 V2 原生识图动作是否已加载。", "image");
      }
    }
    if (!items.length) add("info", "model", "当前范围没有待处理信号", "角色账本、任务路由、Provider 与确认状态暂未发现异常。", "");
    return items;
  }

  function categoryEvidence(key, items, data, stats) {
    data = data || {};
    const runtime = data.runtime || {};
    const actions = Array.isArray(state.integrations?.image?.actions) ? state.integrations.image.actions : [];
    const voices = Array.isArray(state.integrations?.voice?.providers) ? state.integrations.voice.providers : [];
    const flows = Array.isArray(runtime.conversation) ? runtime.conversation : [];
    const materials = Array.isArray(runtime.prompt_materials) ? runtime.prompt_materials : [];
    const storage = runtime.storage || {};
    const proactive = runtime.proactive || {};
    return ({
      all: number(items.length) + " 项信号",
      model: number(items.filter(item => item.category === "model").length) + " 项信号",
      identity: runtime.identity_scope?.token_ledger === "current_role" ? "角色范围已核对" : "等待身份回执",
      tasks: number(items.filter(item => item.category === "tasks").length) + " 项信号",
      proactive: number(proactive.calls) + " 条已记录",
      image_generation: actions.some(row => row.action === "generate" && row.registered && row.current) ? "工具已注册" : "工具未就绪",
      image_recognition: actions.some(row => row.action === "recognize" && row.registered && row.current) ? "工具已注册" : "工具未就绪",
      voice: voices.length ? number(voices.length) + " 个 Provider" : "暂无 Provider",
      storage: storage.journal_mode ? String(storage.journal_mode).toUpperCase() : "状态未知",
      delivery: number(flows.length) + " 条轨迹",
      prompt: number(materials.length) + " 类来源",
      budget: data.budget?.soft_limit_enabled ? "软限额已开" : "软限额未开",
      cache: Number(stats?.cacheTelemetryCalls) > 0 ? (Number(stats?.cacheCoverage) >= 100 ? "已收回执" : "部分覆盖") : "等待回执",
    })[key] || "";
  }

  function categoriesMarkup(items, data, stats) {
    return diagnosticCategories.map(([key, label, description]) => {
      const count = key === "all" ? items.length : items.filter(item => item.category === key).length;
      const evidence = categoryEvidence(key, items, data, stats);
      return fmt('<button type="button" data-diagnostic-category="{{0}}" role="tab" aria-selected="{{1}}" class="{{2}}" title="{{3}}"><span>{{4}}</span><b>{{5}}</b><small>{{6}}</small></button>',
        key, state.category === key, state.category === key ? "is-active" : "", escapeHtml(description + " · " + evidence), escapeHtml(label), count, escapeHtml(evidence));
    }).join("");
  }

  function categoryFocusMarkup(data, stats, items) {
    const runtime = data.runtime || {};
    const storage = runtime.storage || {};
    const flows = Array.isArray(runtime.conversation) ? runtime.conversation : [];
    const materials = Array.isArray(runtime.prompt_materials) ? runtime.prompt_materials : [];
    const proactive = runtime.proactive || {};
    const identity = runtime.identity_scope || {};
    const debounce = Array.isArray(runtime.debounce_trace) ? runtime.debounce_trace : [];
    const routes = Array.isArray(state.modelStatus?.tasks) ? state.modelStatus.tasks : [];
    const textProviders = Array.isArray(data.providers) ? data.providers : [];
    const voiceProviders = Array.isArray(state.integrations?.voice?.providers) ? state.integrations.voice.providers : [];
    const imageActions = Array.isArray(state.integrations?.image?.actions) ? state.integrations.image.actions : [];
    const currentCategory = state.category;
    const category = diagnosticCategories.find(item => item[0] === currentCategory) || diagnosticCategories[0];
    let facts = [];
    let actions = [];
    let note = "";
    const addAction = (target, label) => actions.push({target, label});
    if (currentCategory === "model") {
      facts = [["失败调用", number(stats.failures)], ["待确认", number(stats.unconfirmed + stats.unknown)], ["文本 Provider", number(textProviders.length)]];
      addAction("test-zone", "测试 Provider"); addAction("task-audit", "检查任务路由");
      note = "未知结果保留在账本中，不会自动重放。";
    } else if (currentCategory === "tasks") {
      facts = [["已配置任务", number(routes.length)], ["路由信号", number(items.filter(item => item.category === "tasks").length)], ["后台软限额", data.budget?.soft_limit_enabled ? "已启用" : "未启用"]];
      addAction("task-audit", "查看任务路由"); addAction("budget-block", "查看后台限额");
      note = "任务路由检查只读取 Provider 与能力元数据。";
    } else if (currentCategory === "identity") {
      const identity = runtime.identity_scope || {};
      facts = [["管理身份", identity.dashboard_operator === "verified" ? "已验证" : "未知"],
        ["V2 管理授权", identity.role_access === "verified" ? "已通过" : "未知"],
        ["用量范围", identity.token_ledger === "current_role" ? "当前角色" : "未知"]];
      addAction("identity-evidence", "查看隔离证据");
      note = "仅展示这次已授权请求的校验状态，不输出身份、账号或会话标识。";
    } else if (currentCategory === "delivery") {
      const failed = flows.reduce((sum, row) => sum + (Number(row.failed_parts) || 0), 0);
      const unknown = flows.reduce((sum, row) => sum + (Number(row.unknown_parts) || 0), 0);
      const debounce = Array.isArray(runtime.debounce_trace) ? runtime.debounce_trace : [];
      facts = [["收口轨迹", number(flows.length)], ["投递失败", number(failed)], ["防抖记录", number(debounce.length)]];
      addAction("delivery-evidence", "查看投递轨迹"); addAction("debounce-evidence", "查看消息收口");
      note = "查看等待窗、合并状态与投递回执；不展示消息正文，未知结果不会自动重发。";
    } else if (currentCategory === "proactive") {
      facts = [["已记录触达", number(proactive.calls)], ["最近记录", time(proactive.latest_at)], ["拦截原因", "尚未接入"]];
      addAction("proactive-evidence", "查看触达记录");
      note = "当前 V2 保存触达总数与最近时间，候选评分链尚未接入。";
    } else if (["image_generation", "image_recognition"].includes(currentCategory)) {
      const actionName = currentCategory === "image_generation" ? "generate" : "recognize";
      const found = imageActions.filter(row => row.action === actionName && row.registered && row.current).length;
      facts = [["当前动作", currentCategory === "image_generation" ? "生图" : "识图"], ["已注册", number(found)], ["提交生成请求", "否"]];
      addAction("test-zone", "检查图片工具");
      note = "这里核对扩展声明状态，不会生成或识别真实图片。";
    } else if (currentCategory === "voice") {
      facts = [["TTS Provider", number(voiceProviders.length)], ["最近测试", state.voiceTest?.title || "尚未运行"], ["发送给联系人", "否"]];
      addAction("test-zone", "测试 TTS");
      note = "合成测试只生成短音频，不发送给联系人；Provider 可能计费。";
    } else if (currentCategory === "storage") {
      facts = [["日志模式", String(storage.journal_mode || "未知").toUpperCase()], ["外键", storage.foreign_keys ? "开启" : "关闭"], ["最近检查", state.storageTest?.title || "尚未运行"]];
      addAction("storage-block", "运行只读检查");
      note = "完整性检查使用 quick_check 与外键核对，不修改数据库。";
    } else if (currentCategory === "prompt") {
      facts = [["材料来源", number(materials.length)], ["统计范围", "最近 20 条输入"], ["显示正文", "从不展示"]];
      addAction("prompt-evidence", "查看来源元数据");
      note = "仅列来源、用途与纳入状态，不保留提示词或消息正文。";
    } else if (currentCategory === "budget") {
      const budget = data.budget || {};
      facts = [["已入账", number(budget.spent_tokens)], ["预留中", number(budget.held_tokens)], ["硬上限", number(budget.limit_tokens)]];
      addAction("budget-block", "查看预算配置");
      note = "后台软限额只影响新建的可选任务；正在运行的任务会继续完成。";
    } else if (currentCategory === "cache") {
      facts = [["命中率", percent(stats.cacheRate)], ["确认覆盖", percent(stats.cacheCoverage)], ["低命中样本", number(recentRows(data).filter(row => row.cache_hit_rate != null && Number(row.input_tokens) >= 1000 && Number(row.cache_hit_rate) < 20).length)]];
      addAction("cache-panel", "查看缓存诊断"); addAction("low-cache-calls", "查看低命中调用");
      note = "这里只能读 Provider 回执；前缀变化未采集，不据此判定缓存破坏。";
    } else {
      facts = [["错误", number(items.filter(item => item.severity === "error").length)], ["警告", number(items.filter(item => item.severity === "warn").length)], ["已配置任务", number(routes.length)]];
      addAction("test-zone", "打开链路测试"); addAction("task-audit", "检查模型路由");
      note = "检查数据限定为已选 V2 身份与角色。";
    }
    const factMarkup = facts.map(([label, value]) => fmt('<div><span>{{0}}</span><strong>{{1}}</strong></div>', escapeHtml(label), escapeHtml(value))).join("");
    const actionMarkup = actions.map(item => item.target === "low-cache-calls"
      ? '<button type="button" data-set-call-filter="cache-low">' + escapeHtml(item.label) + '</button>'
      : fmt('<button type="button" data-focus-panel="{{0}}">{{1}}</button>', item.target, escapeHtml(item.label))).join("");
    return '<section class="maint-diagnostic-focus" data-category="' + escapeHtml(currentCategory) + '"><div class="maint-diagnostic-focus-copy"><span class="maint-eyebrow">FOCUS / ' + escapeHtml(category[1]) + '</span><h4>' + escapeHtml(category[1]) + '工作区</h4><p>' + escapeHtml(note) + '</p></div><div class="maint-diagnostic-focus-facts">' + factMarkup + '</div><div class="maint-diagnostic-focus-actions">' + actionMarkup + '</div></section>';
  }

  function timelineMarkup(data) {
    const events = [];
    for (const row of recentRows(data)) {
      const rowCategory = row.kind === "conversation.reply" ? "model" : "tasks";
      if (row.failure) events.push({severity: "error", category: rowCategory, title: failureName(row.failure), row});
      else if (row.state === "unknown" || row.tokens == null) events.push({severity: "warn", category: rowCategory, title: "用量或结果未确认", row});
      else if (["reserved", "dispatched"].includes(row.state)) events.push({severity: "warn", category: rowCategory, title: "调用尚未收束", row});
      if (row.cache_hit_rate != null && Number(row.input_tokens) >= 1000 && Number(row.cache_hit_rate) < 20) {
        events.push({severity: "info", category: "cache", title: "缓存命中 " + row.cache_hit_rate + "%", row});
      }
      if (events.length >= 12) break;
    }
    for (const row of (data.runtime?.conversation || [])) {
      if (row.failed_parts) events.push({severity: "error", category: "delivery", title: "回复片段投递失败", at: row.created_at,
        detail: number(row.failed_parts) + " 个失败 · " + number(row.input_count) + " 条输入"});
      else if (row.unknown_parts) events.push({severity: "warn", category: "delivery", title: "回复投递回执未知", at: row.created_at,
        detail: number(row.unknown_parts) + " 个结果未知 · 不自动重发"});
      else if (row.flow_state === "blocked" || row.flow_state === "closed") events.push({severity: "warn", category: "delivery", title: "消息收口 " + row.flow_state,
        at: row.created_at, detail: row.flow_reason || "流程已结束"});
      else if (row.delivered_parts) events.push({severity: "info", category: "delivery", title: "回复已收到投递回执", at: row.created_at,
        detail: number(row.delivered_parts) + " / " + number(row.part_count) + " 个片段已送达"});
    }
    events.sort((a, b) => String(b.at || b.row?.at || "").localeCompare(String(a.at || a.row?.at || "")));
    const visible = events.filter(item => (state.category === "all" || state.category === item.category)
      && (state.severity === "all" || state.severity === item.severity));
    if (!visible.length) return '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>这个问题类型与严重程度下，没有对应的近期事件回执。</p></div>';
    return '<div class="maint-event-list">' + visible.slice(0, 16).map(item => {
      const detail = item.row ? taskName(item.row.kind) + " · " + (item.row.provider || "未知 Provider") + " · " + stateName(item.row.state) : item.detail;
      return fmt('<article data-severity="{{0}}" data-category="{{1}}"><i></i><time>{{2}}</time><div><strong>{{3}}</strong><small>{{4}}</small></div></article>',
        item.severity, item.category, escapeHtml(time(item.at || item.row?.at)), escapeHtml(item.title), escapeHtml(detail));
    }).join("") + "</div>";
  }

  function operationsMarkup(data) {
    const runtime = data.runtime || {};
    const storage = runtime.storage || {};
    const flows = Array.isArray(runtime.conversation) ? runtime.conversation : [];
    const materials = Array.isArray(runtime.prompt_materials) ? runtime.prompt_materials : [];
    const proactive = runtime.proactive || {};
    const identity = runtime.identity_scope || {};
    const debounce = Array.isArray(runtime.debounce_trace) ? runtime.debounce_trace : [];
    const sync = ({0: "关闭", 1: "普通", 2: "完整", 3: "额外完整"})[storage.synchronous] || "未知";
    const category = state.category;
    const show = (categories) => category === "all" || categories.includes(category);
    const flowRows = flows.length ? flows.slice(0, 6).map(row => {
      const tone = row.failed_parts ? "error" : row.unknown_parts || row.pending_parts || row.flow_state === "blocked" ? "warn" : "ok";
      return fmt('<article data-state="{{0}}"><time>{{1}}</time><strong>{{2}} · {{3}}</strong><small>{{4}} 输入 · {{5}} 已送达 / {{6}} 失败 / {{7}} 未知</small></article>',
        tone, escapeHtml(time(row.created_at)), escapeHtml(row.flow_state || row.batch_state), escapeHtml(row.flow_reason || "消息收口"),
        number(row.input_count), number(row.delivered_parts), number(row.failed_parts), number(row.unknown_parts));
    }).join("") : '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>当前角色没有已保存的消息收口轨迹。</p></div>';
    const materialRows = materials.length ? materials.slice(0, 8).map(row => fmt(
      '<article><span>{{0}}<small>{{1}}</small></span><b>{{2}}</b><i>{{3}} 次</i></article>',
      escapeHtml(row.owner), escapeHtml(row.purpose), escapeHtml(row.state), number(row.uses))).join("") :
      '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>最近 20 条输入没有可列出的上下文材料元数据。</p></div>';
    const proofState = value => value === "verified" || value === "current_role" ? "ok" : "unknown";
    const identityRows = [
      ["管理身份", identity.dashboard_operator, "Dashboard 登录校验"],
      ["V2 管理授权", identity.role_access, "当前管理角色授权"],
      ["Token 账本", identity.token_ledger, "当前角色范围"],
    ].map(([label, value, detail]) => fmt(
      '<article data-state="{{0}}"><i></i><span><strong>{{1}}</strong><small>{{2}}</small></span><b>{{3}}</b></article>',
      proofState(value), escapeHtml(label), escapeHtml(detail),
      value === "verified" ? "已验证" : value === "current_role" ? "已隔离" : "未知")).join("");
    const debounceRows = debounce.length ? debounce.map(row => {
      const tone = row.flow_state === "blocked" ? "warn" : ["complete", "closed"].includes(row.flow_state) ? "ok" : "active";
      const timing = [
        row.quiet_window_ms == null ? "安静窗未记录" : "安静窗 " + number(row.quiet_window_ms) + " ms",
        row.merge_window_ms == null ? "合并上限未记录" : "合并上限 " + number(row.merge_window_ms) + " ms",
      ].join(" · ");
      return fmt('<article data-state="{{0}}"><time>{{1}}</time><div><strong>{{2}} · {{3}}</strong><small>{{4}} 条输入 / {{5}} 个片段 · {{6}}</small></div><span>{{7}}</span></article>',
        tone, escapeHtml(time(row.at)), escapeHtml(flowStateName(row.flow_state)), escapeHtml(flowReasonName(row.reason)),
        number(row.input_count), number(row.part_count), escapeHtml(timing),
        row.flow_state === "collecting" ? "预计收口 " + time(row.due_at) : "时限 " + time(row.deadline_at));
    }).join("") : '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>当前角色还没有可展示的消息收口防抖轨迹。</p></div>';
    const sections = [];
    if (show(["identity"])) sections.push('<section data-evidence-kind="identity" data-focus-target="identity-evidence"><div class="maint-subhead"><strong>统一身份与隔离</strong><span>REQ-041 / 本次管理请求</span></div>' +
      '<div class="maint-identity-checks">' + identityRows + '</div><p class="maint-evidence-note">只显示鉴权与账本边界的通过状态，不返回身份、账号、会话或角色标识。</p></section>');
    if (show(["storage", "model"])) sections.push('<section data-evidence-kind="storage" data-focus-target="storage-block"><div class="maint-subhead"><strong>V2 SQLite 存储</strong><span>' +
      escapeHtml(String(storage.journal_mode || "状态未知").toUpperCase()) + '</span></div><div class="maint-evidence-stats">' +
      '<div><span>同步级别</span><b>' + escapeHtml(sync) + '</b></div><div><span>锁等待</span><b>' + number(storage.busy_timeout_ms) + ' ms</b></div>' +
      '<div><span>外键</span><b>' + (storage.foreign_keys ? "开启" : "关闭") + '</b></div><div><span>数据库页</span><b>' + number(storage.page_count) + '</b></div></div>' +
      '<div class="maint-storage-check"><button type="button" class="maint-probe-button" data-storage-test ' + (state.storageTesting ? "disabled" : "") + '><i data-lucide="database-zap"></i><span>' +
      (state.storageTesting ? "检查中" : "运行 SQLite 完整检查") + '</span></button><small>只读执行 quick_check 与外键一致性检查；不修改数据库。</small></div>' + resultMarkup(state.storageTest) + '</section>');
    if (show(["delivery", "model"])) sections.push('<section data-evidence-kind="delivery" data-focus-target="delivery-evidence"><div class="maint-subhead"><strong>消息收口与投递</strong><span>当前身份 / 角色范围</span></div><div class="maint-evidence-flow">' + flowRows + '</div></section>');
    if (show(["delivery"])) sections.push('<section data-evidence-kind="debounce" data-focus-target="debounce-evidence"><div class="maint-subhead"><strong>消息聚合与防抖追踪</strong><span>最近 ' + number(debounce.length) + ' 条</span></div>' +
      '<div class="maint-debounce-list">' + debounceRows + '</div><p class="maint-evidence-note">只显示收口状态、等待窗和计数；不展示消息内容。未知投递结果不会在这里触发重发。</p></section>');
    if (show(["prompt", "model"])) sections.push('<section data-evidence-kind="prompt" data-focus-target="prompt-evidence"><div class="maint-subhead"><strong>上下文注入来源</strong><span>最近 20 条输入</span></div><p class="maint-evidence-note">只显示材料来源与状态，不显示任何提示词、消息或注入正文。</p><div class="maint-material-list">' + materialRows + '</div></section>');
    if (show(["proactive"])) sections.push('<section data-evidence-kind="proactive" data-focus-target="proactive-evidence"><div class="maint-subhead"><strong>主动触达记录</strong><span>当前身份 / 角色范围</span></div><div class="maint-proactive-snapshot"><strong>' + number(proactive.calls) + '</strong><span>条已记录主动触达</span><small>最近记录 · ' + escapeHtml(time(proactive.latest_at)) + '</small></div><p class="maint-evidence-note">主动候选拦截原因与完整评分链尚未接入此 V2 面板。</p></section>');
    if (!sections.length) return "";
    return '<details class="maint-evidence-drawer" open><summary><span>运行证据台</span><small>按当前问题类型聚焦</small></summary>' +
      '<div class="maint-evidence-grid">' + sections.join("") + '</div></details>';
  }

  function taskAuditMarkup() {
    const tasks = Array.isArray(state.modelStatus?.tasks) ? state.modelStatus.tasks : [];
    if (!tasks.length) return '<div class="maint-empty"><span class="maint-empty-mark">?</span><p>模型任务快照未读取到；刷新后可检查各任务 Provider 路由。</p></div>';
    const providers = new Map((Array.isArray(state.modelStatus.providers) ? state.modelStatus.providers : []).map(item => [item.id, item]));
    return '<div class="maint-task-audit-list">' + tasks.map(task => {
      const primary = String(task.fields?.provider?.value || "");
      const fallback = String(task.fields?.fallback?.value || "");
      const route = providers.get(primary);
      const required = Array.isArray(task.capabilities) ? task.capabilities : [];
      const compatible = route && required.every(capability => (route.capabilities || []).includes(capability));
      const outputLimit = Number(task.fields?.max_output_tokens?.value) || 0;
      const outputFits = !route || !outputLimit || outputLimit <= Number(route.max_output_tokens || 0);
      const result = !primary || !route ? "warn" : !compatible || !outputFits ? "error" : "ok";
      const label = result === "ok" ? "路由正常" : result === "error" ? "能力或上限不匹配" : "Provider 不可用";
      const routeText = primary ? primary + (fallback ? " · 备用 " + fallback : " · 无备用") : "未设置主 Provider";
      const meta = [required.join(" + ") || "无额外能力", task.application_state || "应用状态未知"].join(" · ");
      return fmt('<article data-state="{{0}}"><div><strong>{{1}}</strong><small>{{2}} · {{3}}</small></div><span>{{4}}</span></article>',
        result, escapeHtml(taskName(task.kind)), escapeHtml(routeText), escapeHtml(meta), escapeHtml(label));
    }).join("") + "</div>";
  }

  function resultMarkup(item) {
    if (!item) return "";
    const elapsed = item.latency_ms ?? item.elapsed_ms;
    const facts = [];
    if (elapsed != null) facts.push("耗时 " + number(elapsed) + " ms");
    if (item.code) facts.push("错误码 " + String(item.code));
    if (Array.isArray(item.integrity)) facts.push("完整性 " + item.integrity.join(" · "));
    if (item.foreign_key_issues != null) facts.push("外键问题 " + number(item.foreign_key_issues));
    return '<div class="maint-test-result" data-state="' + escapeHtml(item.status) + '" role="status"><div><strong>' + escapeHtml(item.title) + '</strong><small>' + escapeHtml(item.message) + '</small></div>' +
      (facts.length ? '<ul>' + facts.map(value => '<li>' + escapeHtml(value) + '</li>').join("") + '</ul>' : "") +
      (item.suggestion ? '<p><b>下一步</b> ' + escapeHtml(item.suggestion) + '</p>' : "") + '</div>';
  }

  function integrationsMarkup(data) {
    const voice = state.integrations?.voice;
    const image = state.integrations?.image;
    const tts = Array.isArray(voice?.providers) ? voice.providers : [];
    const allActions = Array.isArray(image?.actions) ? image.actions : [];
    const actions = state.category === "image_generation" ? allActions.filter(item => item.action === "generate")
      : state.category === "image_recognition" ? allActions.filter(item => item.action === "recognize") : allActions;
    const textProviders = Array.isArray(data.providers) ? data.providers : [];
    const showText = ["all", "model", "tasks"].includes(state.category);
    const showVoice = ["all", "voice"].includes(state.category);
    const showImage = ["all", "image_generation", "image_recognition"].includes(state.category);
    const textOptions = textProviders.map(item => fmt('<option value="{{0}}" {{1}}>{{0}}{{2}}</option>',
      escapeHtml(item.id), item.id === state.provider ? "selected" : "", item.model ? " · " + escapeHtml(item.model) : "")).join("");
    const voiceOptions = tts.map(item => fmt('<option value="{{0}}" {{1}}>{{0}}</option>',
      escapeHtml(item.id), item.id === state.voiceProvider ? "selected" : "")).join("");
    const imageOptions = actions.map(item => fmt('<option value="{{0}}" {{1}}>{{0}}</option>',
      escapeHtml(item.action), item.action === state.imageAction ? "selected" : "")).join("");
    let imageResult = null;
    if (state.imageTest) {
      const ok = state.imageTest.registered && state.imageTest.current;
      imageResult = {status: ok ? "ok" : "failed", title: ok ? "注册检查通过" : "注册检查未通过",
        message: state.imageTest.error || (state.imageTest.action + " · " + (state.imageTest.registered ? "已注册" : "未注册") +
          " · " + (state.imageTest.current ? "当前声明有效" : "声明已变化或不可用")),
        suggestion: ok ? "当前动作已就绪，可继续检查调用侧权限与输入。" : "刷新运行态后确认对应扩展已启用并完成注册。"};
    }
    const tests = [];
    if (showText) tests.push('<div class="maint-test-row"><div><strong>文本 Provider</strong><small>固定连接探测，不生成角色回复；服务商可能计费。</small></div><div class="maint-test-controls">' +
      '<select data-provider-select ' + (textOptions ? "" : "disabled") + '>' + (textOptions || '<option value="">无可用 Provider</option>') + '</select>' +
      '<button class="maint-probe-button" type="button" data-provider-probe ' + (!textOptions || state.testing ? "disabled" : "") + '><i data-lucide="' + (state.testing ? "loader-circle" : "scan-line") + '"></i><span>' + (state.testing ? "探测中" : "测试") + '</span></button></div></div>' + resultMarkup(state.test));
    if (showVoice) tests.push('<div class="maint-test-row"><div><strong>TTS 合成</strong><small>合成一句短测试音频但不发送给联系人；服务商可能计费。</small></div><div class="maint-test-controls">' +
      '<select data-voice-provider ' + (voiceOptions ? "" : "disabled") + '>' + (voiceOptions || '<option value="">无可用 TTS</option>') + '</select>' +
      '<select data-voice-language aria-label="测试语音语言"><option value="zh">中文</option><option value="ja">日语</option><option value="en">英语</option></select>' +
      '<button class="maint-probe-button" type="button" data-voice-test ' + (!voiceOptions || state.voiceTesting ? "disabled" : "") + '><i data-lucide="' + (state.voiceTesting ? "loader-circle" : "audio-lines") + '"></i><span>' + (state.voiceTesting ? "合成中" : "测试") + '</span></button></div></div>' + resultMarkup(state.voiceTest));
    if (showImage) tests.push('<div class="maint-test-row"><div><strong>' + (state.category === "image_recognition" ? "识图工具" : "原生图片工具") + '</strong><small>只验证扩展注册状态，不会提交图片生成请求。</small></div><div class="maint-test-controls">' +
      '<select data-image-action ' + (imageOptions ? "" : "disabled") + '>' + (imageOptions || '<option value="">未发现图片工具</option>') + '</select>' +
      '<button class="maint-probe-button" type="button" data-image-test ' + (!imageOptions || state.imageTesting ? "disabled" : "") + '><i data-lucide="' + (state.imageTesting ? "loader-circle" : "image-check") + '"></i><span>' + (state.imageTesting ? "检查中" : "检查") + '</span></button></div></div>' + resultMarkup(imageResult));
    const body = tests.length ? tests.join("") : '<div class="maint-test-empty"><span data-lucide="activity"></span><div><strong>此问题类型没有安全的主动测试</strong><small>检查结果来自运行回执与只读证据；不会对用户发送消息或重放未知请求。</small></div></div>';
    return '<div class="maint-test-zone" data-focus-target="test-zone"><div class="maint-test-head"><span class="maint-eyebrow">LIVE TESTS</span><h4>链路与扩展测试</h4></div>' + body + '</div>';
  }

  function diagnosticFaqMarkup(data, stats) {
    const definitions = {
      all: [
        ["用量未知代表什么？", "账本已记录调用，但 Provider 没有提供可确认的 Token 确认。结果未知不会自动重放，避免重复副作用。", "test-zone", "检查 Provider"],
        ["排障数据来自哪里？", "只读取当前 V2 身份与角色的调用、路由和运行回执；外部插件数据不会混入。", "task-audit", "查看路由"],
        ["测试会产生费用或发送消息吗？", "文本探测与 TTS 合成会调用所选 Provider，可能计费；图片检查与 SQLite 检查只读，不会向联系人发送内容。", "test-zone", "查看测试"],
      ],
      identity: [
        ["REQ-041 结果为什么只显示状态？", "管理身份与角色授权通过后才会返回本页；页面只给出当前请求的校验结论，不显示身份、账号、会话或角色标识。", "identity-evidence", "查看隔离证据"],
        ["Token 统计范围包含哪些对象？", "只包含当前已授权 V2 角色账本。独立插件账本与 AstrBot 主链不会并入预算或成本。", "identity-evidence", "查看账本边界"],
      ],
      model: [
        ["探测通过就代表真实回复正常吗？", "探测只确认 Provider 可响应，不会走角色提示、消息接收和投递链路；异常时再结合调用回执定位。", "test-zone", "测试 Provider"],
        ["结果未知为什么不能重试？", "请求可能已到达 Provider，但回执未能确认。自动重放可能重复计费或产生重复回复，因此保留原记录供核对。", "task-audit", "检查模型路由"],
      ],
      tasks: [
        ["任务路由检查什么？", "核对主/备用 Provider 是否存在、能力是否匹配，以及输出上限是否超过 Provider 声明值；不读取提示词内容。", "task-audit", "查看任务路由"],
        ["后台任务为什么会延后？", "启用软限额后，达到阈值会暂停新建的可选后台任务。已经运行的任务会继续完成。", "budget-block", "查看软限额"],
      ],
      delivery: [
        ["部分片段失败后会自动补发吗？", "未知或失败的投递回执不会自动重发，先核对原收口轨迹与平台回执，再决定是否由用户发起新一轮。", "delivery-evidence", "查看投递轨迹"],
        ["没有投递轨迹表示什么？", "V2 只展示已保存的角色级收口证据；没有记录不代表平台一定没有处理该消息。", "delivery-evidence", "查看收口证据"],
        ["消息为什么会等待后再合并？", "防抖安静窗会把短时间连续输入收进同一轮；最大等待和轮次时限有上界。这里展示状态与时窗，不显示消息正文。", "debounce-evidence", "查看防抖追踪"],
      ],
      proactive: [
        ["为什么没有主动消息？", "这里能核对已记录的主动触达次数与最近时间；静默、冷却、候选评分和拦截原因尚未接入本页。", "proactive-evidence", "查看触达记录"],
        ["能从这里发送测试主动消息吗？", "当前没有安全的主动消息测试接口，因此本页不会发送测试消息。", "proactive-evidence", "查看触达记录"],
      ],
      image_generation: [
        ["注册检查会实际生成图片吗？", "不会。它只核对生图动作是否已注册且声明仍有效，不发起外部生成请求。", "test-zone", "检查生图工具"],
        ["动作未就绪时先检查什么？", "刷新运行快照，确认图片扩展已启用并完成加载，再检查相应动作声明。", "test-zone", "重新检查"],
      ],
      image_recognition: [
        ["注册检查会分析真实图片吗？", "不会。这里检查识图动作的注册状态，不读取聊天图片或图片缓存内容。", "test-zone", "检查识图工具"],
        ["动作已注册但识图仍失败？", "注册状态不覆盖文件可读性、视觉 Provider 能力和调用侧权限；需继续核对对应运行日志。", "test-zone", "检查扩展状态"],
      ],
      voice: [
        ["TTS 测试会把语音发给谁？", "不会发送给联系人。测试仅合成短音频并返回状态；所选服务商可能计费。", "test-zone", "运行 TTS 测试"],
        ["TTS Provider 不可用？", "确认 AstrBot 已加载对应语音 Provider，并检查所选语言绑定后重新探测。", "test-zone", "检查语音绑定"],
      ],
      storage: [
        ["SQLite 检查会修改数据吗？", "不会。检查通过只读快照执行 quick_check 和外键一致性核对。", "storage-block", "运行只读检查"],
        ["WAL 状态异常怎么办？", "先运行完整检查并核对宿主连接状态；不要在页面中清理或重置数据库。", "storage-block", "检查存储"],
      ],
      prompt: [
        ["为什么看不到提示词正文？", "本页只保留材料来源、用途与纳入状态，不显示或记录提示词、消息和注入正文。", "prompt-evidence", "查看来源"],
        ["来源标记 omitted 是什么？", "该轮材料被记录但没有纳入最终上下文；这里只提供来源计数，不推断具体文本原因。", "prompt-evidence", "查看材料状态"],
      ],
      budget: [
        ["软限额会中断正在运行的任务吗？", "不会。软限额只影响达到阈值后新建的可选后台任务；已运行任务继续完成。", "budget-block", "查看限额"],
        ["Provider 余额等于本地预算吗？", "不等于。本页只显示 V2 本地角色预算，当前没有统一授权的 Provider 余额接口。", "budget-block", "查看本地预算"],
      ],
      cache: [
        ["低命中能证明缓存被破坏吗？", "不能。这里只汇总 Provider 实报 Token 与低命中样本；当前未采集前缀变化事件。", "cache-panel", "查看缓存样本"],
        ["参考 Token 成本控制插件的哪些信号？", "按缓存命中、普通输入、缓存写入和 Provider 覆盖率观察成本；提示词、工具定义或上下文顺序变更的签名尚未接入。", "cache-panel", "查看缓存构成"],
      ],
    };
    const items = definitions[state.category] || definitions.all;
    return items.map(item => fmt('<article><div><strong>{{0}}</strong><p>{{1}}</p></div><button type="button" data-focus-panel="{{2}}">{{3}}</button></article>',
      escapeHtml(item[0]), escapeHtml(item[1]), item[2], escapeHtml(item[3]))).join("");
  }

  function diagnosticsMarkup(data, stats) {
    const items = diagnosticItems(data, stats);
    const visible = items.filter(item => (state.category === "all" || item.category === state.category)
      && (state.severity === "all" || item.severity === state.severity));
    const errors = items.filter(item => item.severity === "error").length;
    const warnings = items.filter(item => item.severity === "warn").length;
    const selectedErrors = visible.filter(item => item.severity === "error").length;
    const selectedWarnings = visible.filter(item => item.severity === "warn").length;
    const voice = state.integrations?.voice;
    const image = state.integrations?.image;
    const taskCount = Array.isArray(state.modelStatus?.tasks) ? state.modelStatus.tasks.length : null;
    const routeCount = Array.isArray(state.modelStatus?.providers) ? state.modelStatus.providers.length : null;
    const identityScope = data.runtime?.identity_scope || {};
    const identityReady = identityScope.dashboard_operator === "verified" && identityScope.role_access === "verified"
      && identityScope.token_ledger === "current_role";
    const debounceCount = Array.isArray(data.runtime?.debounce_trace) ? data.runtime.debounce_trace.length : null;
    const runtime = [
      ["all", "管理与记录", number(stats.calls) + " 次调用 · 当前角色隔离", "ok"],
      ["identity", "统一身份与隔离", identityReady ? "授权通过 · 当前角色账本" : "身份或范围未确认", identityReady ? "ok" : "warn"],
      ["tasks", "模型任务", taskCount == null ? "路由状态未知" : number(taskCount) + " 项已配置", taskCount == null ? "unknown" : taskCount ? "ok" : "warn"],
      ["model", "文本 Provider", number((data.providers || []).length) + " 个 V2 适配器" + (routeCount == null ? "" : " · 路由快照已读"), data.providers?.length ? "ok" : "warn"],
      ["delivery", "消息收口", debounceCount == null ? "防抖状态未知" : number(debounceCount) + " 条防抖记录", debounceCount == null ? "unknown" : "ok"],
      ["voice", "TTS Provider", voice ? number((voice.providers || []).length) + " 个已加载" : "状态未知", voice ? "ok" : "unknown"],
      ["image_generation", "图片工具", image ? number((image.actions || []).filter(row => row.registered && row.current).length) + " 个当前注册" : "状态未知", image ? "ok" : "unknown"],
    ].filter(item => state.category === "all" || item[0] === state.category
      || (state.category === "model" && item[0] === "all")
      || (state.category === "image_recognition" && item[0] === "image_generation"));
    const severityButtons = [["all", "全部"], ["error", "错误"], ["warn", "警告"], ["info", "信息"]].map(([key, label]) =>
      fmt('<button type="button" data-diagnostic-severity="{{0}}" aria-pressed="{{1}}" class="{{2}}">{{3}}</button>',
        key, state.severity === key, state.severity === key ? "is-active" : "", label)).join("");
    const issueRows = visible.length ? visible.map(item => {
      let action = "";
      if (item.action === "failed") action = '<button type="button" data-set-call-filter="failed">查看失败</button>';
      if (item.action === "uncertain") action = '<button type="button" data-set-call-filter="uncertain">查看记录</button>';
      if (item.action === "cache-low") action = '<button type="button" data-set-call-filter="cache-low">查看样本</button>';
      if (item.action === "route") action = '<button type="button" data-focus-panel="task-audit">查看路由</button>';
      if (item.action === "identity") action = '<button type="button" data-focus-panel="identity-evidence">查看边界</button>';
      if (item.action === "provider") action = '<button type="button" data-focus-panel="test-zone">定位测试</button>';
      if (item.action === "budget") action = '<button type="button" data-focus-panel="budget-block">查看限额</button>';
      return fmt('<article class="maint-diagnostic-item" data-severity="{{0}}"><span class="maint-severity-mark">{{1}}</span><div><strong>{{2}}</strong><p>{{3}}</p></div>{{4}}</article>',
        item.severity, item.severity === "error" ? "!" : item.severity === "warn" ? "△" : "i",
        escapeHtml(item.title), escapeHtml(item.detail), action);
    }).join("") : '<div class="maint-empty"><span class="maint-empty-mark">✓</span><p>此分类与严重程度下没有待处理信号。</p></div>';
    const audit = ["all", "model", "tasks"].includes(state.category)
      ? '<div class="maint-task-audit" data-focus-target="task-audit"><div class="maint-subhead"><strong>模型任务路由</strong><span>' +
        (taskCount == null ? "状态未知" : number(taskCount) + " 项") + '</span></div>' + taskAuditMarkup() + '</div>' : "";
    const refreshButton = '<button type="button" class="maint-diagnostic-refresh" data-refresh ' + (state.loading ? "disabled" : "") + '><i data-lucide="refresh-cw"></i><span>' + (state.loading ? "正在检查" : "重新检查") + '</span></button>';
    const faqOpen = state.category === "all" ? "" : " open";
    return '<section class="maint-diagnostics-panel" aria-labelledby="maint-diagnostics-heading"><div class="maint-panel-heading"><div><span class="maint-eyebrow">DIAGNOSTICS / 01</span><h3 id="maint-diagnostics-heading">排障与测试</h3></div>' +
      '<div class="maint-diagnostic-heading-actions"><span class="maint-check-state" data-state="' + (errors || warnings ? "warn" : "ok") + '">' + (errors ? errors + " 项错误" : warnings ? warnings + " 项关注" : "运行正常") + '</span>' + refreshButton + '</div></div>' +
      '<div class="maint-diagnostic-summary"><strong>' + (selectedErrors ? selectedErrors + " 项错误待处理" : selectedWarnings ? selectedWarnings + " 项信号待关注" : visible.length ? "当前筛选下没有待处理信号" : "没有待处理信号") + '</strong><span>' + escapeHtml(state.category === "all" ? "全部分类" : (diagnosticCategories.find(item => item[0] === state.category) || ["", "问题类型"])[1]) + ' · 本类 ' + visible.length + ' 项 · 全局错误 ' + errors + ' / 警告 ' + warnings + '</span></div>' +
      '<div class="maint-diagnostic-categories" role="tablist" aria-label="问题类型">' + categoriesMarkup(items, data, stats) + '</div>' +
      categoryFocusMarkup(data, stats, items) +
      '<div class="maint-diagnostic-filter" role="group" aria-label="按严重程度筛选">' + severityButtons + '</div><div class="maint-diagnostic-items">' + issueRows + '</div>' +
      '<div class="maint-diagnostic-lanes"><section class="maint-event-lane"><div class="maint-subhead"><strong>' + (state.category === "all" ? "事件时间线" : "最近 · " + escapeHtml((diagnosticCategories.find(item => item[0] === state.category) || ["", "问题"])[1])) + '</strong><span>当前角色真实回执</span></div>' + timelineMarkup(data) +
      '</section><section class="maint-runtime-lane"><div class="maint-subhead"><strong>运行快照</strong><span>' + escapeHtml(time(data.generated_at)) + '</span></div><div class="maint-runtime-grid">' +
      runtime.map(item => fmt('<div data-state="{{0}}" data-runtime-category="{{1}}"><span>{{2}}</span><strong>{{3}}</strong></div>', item[3], item[0], escapeHtml(item[1]), escapeHtml(item[2]))).join("") +
      '</div><p>当前数据来自 V2 已选角色账本；路由检查仅读元数据。</p>' + audit + '</section></div>' + operationsMarkup(data) + integrationsMarkup(data) +
      '<details class="maint-faq"' + faqOpen + '><summary>诊断说明与常见问题 · ' + escapeHtml((diagnosticCategories.find(item => item[0] === state.category) || ["", "全部"])[1]) + '</summary><div>' + diagnosticFaqMarkup(data, stats) + '</div></details></section>';
  }

  function cacheMarkup(stats, data) {
    const noTelemetry = stats.cacheTelemetryCalls === 0;
    const noHitSamples = stats.cacheCalls === 0;
    const recent = recentRows(data).filter(row => row.cached_input_tokens != null && row.input_tokens != null &&
      Number(row.input_tokens) >= 1000 && Number(row.cache_hit_rate) < 20).slice(0, 5);
    const providers = dimensions(data, stats, "providers").filter(row => row.cache_telemetry_calls || row.cache_reported_calls).slice(0, 5);
    const denominator = Math.max(1, stats.cached + stats.creation + stats.other + stats.output);
    const segments = [["hit", "缓存命中", stats.cached], ["write", "缓存写入", stats.creation],
      ["miss", "普通输入", stats.other], ["output", "输出", stats.output]].map(item =>
      fmt('<span data-part="{{0}}" style="--segment:{{1}}%" title="{{2}} · {{3}} Token"></span>',
        item[0], Math.max(0, Number(item[2]) * 100 / denominator), item[1], number(item[2]))).join("");
    const legend = [["hit", "缓存命中", stats.cached], ["write", "缓存写入", stats.creation],
      ["miss", "普通输入", stats.other], ["output", "输出", stats.output]].map(item =>
      fmt('<span data-part="{{0}}"><i></i>{{1}} <b>{{2}}</b></span>', item[0], item[1], number(item[2]))).join("");
    const providerRows = providers.length ? providers.map(row => fmt('<div><span>{{0}}</span><strong>{{1}}</strong><small>{{2}} 次有可计算确认 · 写入 {{3}}</small></div>',
      escapeHtml(row.key), percent(Number(row.cache_input_tokens) ? Number(row.cached_input_tokens) * 100 / Number(row.cache_input_tokens) : null),
      number(row.cache_reported_calls), number(row.cache_creation_tokens))).join("") :
      '<div class="maint-empty"><span class="maint-empty-mark">—</span><p>当前范围没有 Provider 缓存明细。</p></div>';
    const lowRows = recent.length ? recent.map(row => fmt('<div class="maint-cache-event"><span class="maint-event-mark"><i data-lucide="triangle-alert"></i></span><span><strong>{{0}} · {{1}}</strong><small>{{2}} · {{3}} 输入，命中 {{4}}%</small></span><button type="button" class="maint-text-action" data-set-call-filter="cache-low">查看调用</button></div>',
      escapeHtml(taskName(row.kind)), escapeHtml(row.provider || "Provider"), escapeHtml(time(row.at)), number(row.input_tokens), row.cache_hit_rate)).join("") :
      '<div class="maint-empty"><span class="maint-empty-mark">↗</span><p>' + (noTelemetry ? "收到缓存用量后，这里会列出低命中请求。" : "当前范围没有符合条件的低命中样本。") + '</p></div>';
    const note = noTelemetry
      ? stats.calls === 0 ? "这个范围没有模型调用。收到 Provider 缓存确认后，会显示真实读写与命中数据。" : "当前范围没有缓存字段确认；命中率只在 Provider 同时报告输入量和缓存命中量时计算。"
      : noHitSamples ? "收到缓存相关字段，但没有可计算命中率的完整确认；写入量仍按 Provider 实报展示。"
        : "这里只汇总 Provider 回报的缓存 Token。命中偏低是观察信号，不足以确认缓存失效原因。";
    return '<section class="maint-cache-panel" aria-labelledby="maint-cache-heading"><div class="maint-panel-heading"><div><span class="maint-eyebrow">CACHE / 02</span><h3 id="maint-cache-heading">缓存诊断</h3></div>' +
      fmt('<span class="maint-cache-chip" data-state="{{0}}">{{1}}</span></div><div class="maint-cache-overview"><div class="maint-cache-rate"><strong>{{2}}</strong><span>有效输入的缓存命中</span><div class="maint-cache-meter" role="progressbar" aria-label="缓存命中率" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{{3}}"><span style="--cache-rate:{{3}}%"></span></div></div>',
        noTelemetry || noHitSamples || stats.cacheRate == null ? "unknown" : stats.cacheRate < 40 ? "warn" : "ok",
        noTelemetry ? "等待确认" : stats.cacheRate == null ? "暂无命中率" : percent(stats.cacheRate) + " 命中",
        stats.cacheRate == null ? "—" : percent(stats.cacheRate), stats.cacheRate || 0) +
      '<div class="maint-cache-measures"><div><span>缓存读取</span><strong>' + number(stats.cached) + '</strong></div><div><span>缓存写入</span><strong>' + number(stats.creation) +
      '</strong></div><div><span>普通输入</span><strong>' + number(stats.other) + '</strong></div><div><span>确认覆盖</span><strong>' + percent(stats.cacheCoverage) +
      '</strong></div></div></div><div class="maint-cache-composition" role="img" aria-label="缓存命中、缓存写入、普通输入与输出 Token 构成">' + segments + '</div><div class="maint-cache-legend">' + legend + '</div><p class="maint-cache-note">' + escapeHtml(note) +
      '</p><div class="maint-cache-events"><div class="maint-subhead"><strong>Provider 缓存表现</strong><span>按所选时间范围汇总</span></div><div class="maint-cache-provider-list">' + providerRows +
      '</div></div><div class="maint-cache-events"><div class="maint-subhead"><strong>低命中样本</strong><span>输入 ≥ 1,000 Token，命中率低于 20%</span></div><div class="maint-cache-event-list">' + lowRows +
      '</div></div><div class="maint-cache-caveat"><span>缓存前缀诊断</span><strong>签名状态 · 未采集</strong><div class="maint-cache-signature-grid"><div><span>上下文重置</span><strong>未采集</strong></div><div><span>system prompt</span><strong>未采集</strong></div><div><span>工具定义</span><strong>未采集</strong></div><div><span>顺序漂移</span><strong>未采集</strong></div></div><small>当前账本没有保存提示词、system prompt、工具 schema 或顺序签名，因此无法判断这些变化是否发生。低命中率可用于定位样本，不能单独证明缓存失效。</small></div></section>';
  }

  function render() {
    if (!root || !state) return;
    if (!state.data && state.loading) {
      root.innerHTML = '<div class="maint-loading"><span class="maint-loading-mark"><i data-lucide="activity"></i></span><strong>正在读取角色账本与运行快照</strong><span class="maint-loading-line"></span></div>';
      window.lucide?.createIcons?.();
      return;
    }
    if (!state.data && state.error) {
      root.innerHTML = '<div class="maint-error" role="alert"><i data-lucide="cloud-off"></i><div><strong>维护面板暂时离线</strong><p>' + escapeHtml(state.error) + '</p></div><button class="maint-probe-button" type="button" data-refresh>重新读取</button></div>';
      window.lucide?.createIcons?.();
      return;
    }
    const data = state.data || {};
    const stats = statsFor(data);
    const periodComparison = comparisonMarkup(usageComparison(data, stats));
    const budget = data.budget || {};
    const limit = Math.max(0, Number(budget.limit_tokens) || 0);
    const spent = Math.max(0, Number(budget.spent_tokens) || 0);
    const held = Math.max(0, Number(budget.held_tokens) || 0);
    const budgetPct = limit ? Math.min(100, Math.round((spent + held) * 100 / limit)) : 0;
    const softLimit = Math.max(0, Number(budget.soft_limit_tokens) || 0);
    const softEnabled = Boolean(budget.soft_limit_enabled && softLimit);
    const softPct = softEnabled ? Math.min(100, Math.round((spent + held) * 100 / softLimit)) : 0;
    const softState = !softEnabled ? "off" : spent + held >= softLimit ? "warn" : "ok";
    const today = localDay(data.generated_at);
    const label = ({today: "今日", "7d": "近 7 日", "30d": "近 30 日", total: "全部历史"})[state.period]
      || (state.period === "date" ? stats.day : "今日");
    const providerRows = dimensions(data, stats, "providers");
    const taskRows = dimensions(data, stats, "tasks");
    const externalSource = data.external_token_sources?.[state.tokenSource];
    const tokenScopeNote = state.tokenSource === "companion" ? "V2 当前角色账本 · 仅当前角色"
      : externalSource?.available ? (externalSource.display_name || "外部插件") + " 独立账本 · 不计入 V2 角色预算"
        : "所选来源暂不可用 · 当前角色数据不会代替它";
    const role = window.CompanionProduct?.role()?.role_id || "V2";
    const chartData = Array.isArray(data.daily) ? data.daily : [];
    root.innerHTML = '<div class="maint-board"><header class="maint-board-head"><div class="maint-board-copy"><span class="maint-eyebrow">COMPANION / SIGNAL ROOM</span><h2>运行态势</h2><p>用量、缓存与链路信号，按当前角色账本实时展开。</p></div>' +
      '<div class="maint-board-actions"><span class="maint-live" data-state="' + (state.error ? "warn" : "ok") + '"><i></i>' + (state.loading ? "正在同步" : state.error ? "同步异常" : "已连接") +
      '</span><span class="maint-updated">同步于 ' + escapeHtml(time(data.generated_at)) + '</span><button class="maint-export" type="button" data-export-tokens ' + (state.tokenSource === "companion" ? "" : "disabled") + ' title="导出当前统计 CSV"><i data-lucide="download"></i><span>导出 CSV</span></button><button class="maint-refresh" type="button" data-refresh ' + (state.loading ? "disabled" : "") + ' aria-label="刷新运行统计" title="刷新运行统计"><i data-lucide="refresh-cw"></i><span>' + (state.loading ? "同步中" : "刷新") +
      '</span></button></div></header><section class="maint-token-section" aria-labelledby="maint-usage-heading"><div class="maint-panel-heading"><div><span class="maint-eyebrow">TOKENS / 00</span><h3 id="maint-usage-heading">Token 统计管理</h3><p class="maint-scope-note"><i data-lucide="shield-check"></i> ' +
      escapeHtml(tokenScopeNote) +
      '</p><details class="maint-source-details"><summary><i data-lucide="layers-3"></i><span>统计口径</span></summary><div class="maint-source-grid"><article data-state="active"><span>纳入统计</span><strong>当前角色的 V2 模型任务</strong><small>Provider、任务、缓存确认与本地计价</small></article><article data-state="limited"><span>未纳入本页</span><strong>AstrBot 主链与独立插件账本</strong><small>不跨角色拼接，也不回读其他版本的历史记录</small></article></div></details></div></div>' +
      '<div class="maint-source-tabs" role="tablist" aria-label="Token 统计来源">' + sourceTabsMarkup() + '</div>' +
      sourceComparisonMarkup(data, stats) +
      (state.tokenSource === "companion" ? ('<div class="maint-token-source-note"><i data-lucide="info"></i><span>来源切换只影响 Token 统计；排障、缓存与最近调用始终限定为 V2 当前角色。Provider 账户余额接口尚未接入。</span></div>' +
      '<div class="maint-balance-availability"><div><i data-lucide="wallet-cards"></i><span><small>ACCOUNT BALANCE</small><strong>Provider 余额 · 未接入</strong></span></div><p>当前模型接口没有统一授权的余额查询能力；硬预算与后台软限额仍按本地角色账本统计。</p></div>' +
      '<div class="maint-token-controls"><div class="maint-periods" role="group" aria-label="Token 统计视图">' +
      [["today", "今日"], ["7d", "7 日"], ["30d", "30 日"], ["total", "总计"], ["date", "按日期"]].map(item => fmt('<button type="button" data-period="{{0}}" aria-pressed="{{1}}" class="{{2}}">{{3}}</button>',
        item[0], state.period === item[0], state.period === item[0] ? "is-active" : "", item[1])).join("") +
      '</div><label class="maint-date-control"><span>查看日期</span><input type="date" data-selected-date value="' + escapeHtml(state.selectedDate || today) + '" max="' + escapeHtml(today) + '" ' + (state.period === "date" ? "" : "disabled") + '></label></div>' +
      '<div class="maint-token-hero"><div class="maint-usage-total"><span>' + escapeHtml(label) + ' · Token 总量</span><strong>' + number(stats.tokens) + '</strong><small>Token</small><div class="maint-usage-subline"><span>' + number(stats.calls) +
      ' 次调用</span><i></i><span>' + cost(stats.cost) + ' 本地计价</span></div></div><div class="maint-budget-block"><div class="maint-budget-meter" style="--budget-progress:' + budgetPct +
      '%" role="progressbar" aria-label="今日角色 Token 硬预算" aria-valuemin="0" aria-valuemax="' + limit + '" aria-valuenow="' + Math.min(limit, spent + held) + '"><div class="maint-budget-meter-center"><strong>' +
      budgetPct + '%</strong><span>今日硬预算</span></div></div><div class="maint-budget-caption"><span>已入账 <b>' + number(spent) + '</b></span><span>预留中 <b>' + number(held) + '</b></span><span>上限 <b>' + number(limit) +
      '</b></span></div><div class="maint-soft-limit" data-state="' + softState + '"><div><span>后台软限额</span><strong>' + (softEnabled ? softPct + '%' : "关闭") + '</strong></div><div class="maint-soft-meter"><i style="--soft-progress:' + softPct + '%"></i></div><small>' +
      (softEnabled ? softPct >= 100 ? "已触发 · 暂缓新建可选后台任务" : "阈值 " + number(softLimit) + " Token · 不影响正在运行的任务" : "未启用 · 不限制可选后台任务") + '</small></div></div><div class="maint-token-kpis"><div><span>输入 / 输出</span><strong>' + number(stats.input) + ' / ' + number(stats.output) + '</strong></div><div><span>平均每次</span><strong>' +
      (stats.calls ? number(stats.tokens / stats.calls) : "—") + ' Token</strong></div><div><span>平均延迟</span><strong>' + (stats.latency == null ? "—" : number(stats.latency) + " ms") +
      '</strong></div><div><span>失败 / 未确认</span><strong>' + number(stats.failures) + ' / ' + number(stats.unconfirmed) + '</strong></div></div></div>' + periodComparison +
      '<div class="maint-trend-grid"><section class="maint-trend-panel"><div class="maint-subhead"><strong>每日用量趋势</strong><span>选择柱条可查看对应日期</span></div>' + chart(chartData) +
      '</section><section class="maint-trend-panel"><div class="maint-subhead"><strong>' + escapeHtml(state.period === "date" ? label + "小时分布" : "近 48 小时") + '</strong><span>' + (state.period === "date" ? "按确认时间汇总" : "点选时段查看该小时调用") + '</span></div>' + trendHourlyMarkup(data, stats) +
      '</section></div><div class="maint-rank-grid"><section class="maint-rank-panel"><div class="maint-subhead"><strong>Provider 消耗排行</strong><span>' + number(providerRows.length) + ' 项</span></div>' + rankingMarkup(providerRows, "providers") +
      '<details class="maint-dimension-details"><summary>展开 Provider 明细</summary>' + detailTable(providerRows, "providers") + '</details></section><section class="maint-rank-panel"><div class="maint-subhead"><strong>任务消耗排行</strong><span>' +
      number(taskRows.length) + ' 项</span></div>' + rankingMarkup(taskRows, "tasks") + '<details class="maint-dimension-details"><summary>展开任务明细</summary>' + detailTable(taskRows, "tasks") +
      '</details></section></div><section class="maint-history-panel"><div class="maint-subhead"><strong>每日明细</strong><span>最近 30 日；可用日期选择器检索历史</span></div>' + historyMarkup(data) +
      '</section>') : externalTokenMarkup(state.tokenSource)) + '</section>' + promptWorkspaceMarkup() + '<div class="maint-maintenance-grid">' + diagnosticsMarkup(data, stats) + cacheMarkup(stats, data) + '</div>' +
      '<section class="maint-recent-panel" aria-labelledby="maint-recent-heading"><div class="maint-panel-heading"><div><span class="maint-eyebrow">TRACE / 03</span><h3 id="maint-recent-heading">最近调用</h3></div><div class="maint-trace-controls"><span class="maint-recent-count">' +
      number(matchingRecent(data).length) + ' / ' + number((data.recent || []).length) + ' 条</span><input type="search" data-call-search aria-label="搜索 Provider、任务、失败类型或日期" placeholder="筛 Provider / 任务 / 失败" value="' + escapeHtml(state.callQuery) + '"><select data-call-filter aria-label="筛选最近调用"><option value="all" ' + (state.callFilter === "all" ? "selected" : "") + '>全部记录</option><option value="failed" ' + (state.callFilter === "failed" ? "selected" : "") +
      '>失败</option><option value="uncertain" ' + (state.callFilter === "uncertain" ? "selected" : "") + '>未确认</option><option value="cache-low" ' + (state.callFilter === "cache-low" ? "selected" : "") + '>低缓存命中</option></select>' +
      (state.traceFilter ? '<button type="button" class="maint-text-action" data-clear-trace>清除排行筛选</button>' : "") + '<button type="button" class="maint-text-action" data-toggle-calls>' + (state.showAllCalls ? "收起" : "查看更多") +
      '</button></div></div>' + (state.traceFilter ? '<div class="maint-trace-filter-note">已按排行筛选：' + escapeHtml(state.traceFilter.kind === "tasks" ? taskName(state.traceFilter.key) : state.traceFilter.key) + '</div>' : "") +
      (state.selectedHour ? '<div class="maint-trace-filter-note">已聚焦时段：' + escapeHtml(state.selectedHour.replace("T", " ") + ":00") + ' <button type="button" class="maint-text-action" data-clear-hour>清除时段</button></div>' : "") +
      recentMarkup(data) + '</section><footer class="maint-board-footer"><span>当前角色 / ' + escapeHtml(role) + '</span><span>数据源：V2 模型调用账本 · 成本为本地计价 · 缓存字段来自 Provider 确认</span></footer></div>';
    if (!state.provider && data.providers?.[0]) state.provider = data.providers[0].id;
    if (!state.voiceProvider && state.integrations?.voice?.providers?.[0]) state.voiceProvider = state.integrations.voice.providers[0].id;
    if (!state.imageAction && state.integrations?.image?.actions?.[0]) state.imageAction = state.integrations.image.actions[0].action;
    window.lucide?.createIcons?.();
  }

  async function refresh() {
    if (!state || state.loading) return;
    const current = state;
    const ticket = generation;
    current.loading = true;
    current.error = "";
    render();
    try {
      const path = modelPath();
      const values = await Promise.allSettled([api("GET", path + "/maintenance"), api("GET", path + "/voice"),
        api("GET", path + "/image"), api("GET", path)]);
      if (ticket !== generation || state !== current) return;
      if (values[0].status === "rejected") throw values[0].reason;
      const data = values[0].value;
      if (!data || !data.summary || !Array.isArray(data.daily)) throw new Error("返回的数据结构不完整。");
      current.data = data;
      current.integrations = {
        voice: values[1].status === "fulfilled" ? values[1].value : null,
        image: values[2].status === "fulfilled" ? values[2].value : null,
      };
      if (values[3].status === "fulfilled") current.modelStatus = values[3].value;
      current.provider = current.provider || data.providers?.[0]?.id || "";
      current.voiceProvider = current.voiceProvider || current.integrations.voice?.providers?.[0]?.id || "";
      current.imageAction = current.imageAction || current.integrations.image?.actions?.[0]?.action || "";
    } catch (error) {
      if (ticket !== generation || state !== current) return;
      current.error = error.message || "读取失败，请刷新后重试。";
    } finally {
      if (ticket === generation && state === current) { current.loading = false; render(); }
    }
  }

  async function probe() {
    if (!state || state.testing || !state.provider) return;
    const current = state;
    const ticket = generation;
    current.testing = true;
    current.test = null;
    render();
    try {
      const result = await api("POST", modelPath() + "/test", {provider_id: current.provider});
      if (ticket !== generation || state !== current) return;
      current.test = {...result, status: result.status || "unknown", title: result.status === "ok" ? "文本 Provider 探测通过" : "文本 Provider 探测未通过",
        message: result.status === "ok" ? number(result.latency_ms) + " ms · 未生成角色回复，服务商可能计费。" : routeError(result.code),
        suggestion: result.status === "ok" ? "Provider 可响应；若真实回复仍失败，请继续检查任务路由与回执。" : "核对 Provider 是否在线、接口配置和当前网络后再运行探测。"};
    } catch (error) {
      if (ticket !== generation || state !== current) return;
      current.test = {status: "failed", code: error.code || "model_probe_failed", title: "文本 Provider 探测失败", message: error.message || "探测失败。",
        suggestion: "核对 Provider 状态与接口配置后重试。"};
    } finally {
      if (ticket === generation && state === current) { current.testing = false; render(); }
    }
  }

  async function testVoice() {
    if (!state || state.voiceTesting || !state.voiceProvider) return;
    const current = state;
    const ticket = generation;
    current.voiceTesting = true;
    current.voiceTest = null;
    render();
    try {
      const result = await api("POST", modelPath() + "/voice/test", {provider_id: current.voiceProvider, language: current.voiceLanguage});
      if (ticket !== generation || state !== current) return;
      current.voiceTest = {...result, status: result.status || "unknown", title: result.status === "ok" ? "TTS 合成通过" : "TTS 合成未通过",
        message: result.status === "ok" ? number(result.latency_ms) + " ms · 测试音频未发送给联系人。" : routeError(result.code),
        suggestion: result.status === "ok" ? "当前 TTS Provider 已完成测试合成。" : "检查 AstrBot 中 Provider 是否加载，并确认语言绑定后重试。"};
    } catch (error) {
      if (ticket !== generation || state !== current) return;
      current.voiceTest = {status: "failed", code: error.code || "model_voice_probe_failed", title: "TTS 合成失败", message: error.message || "合成测试失败。",
        suggestion: "检查语音 Provider 是否加载，以及所选语言是否已配置。"};
    } finally {
      if (ticket === generation && state === current) { current.voiceTesting = false; render(); }
    }
  }

  async function testImage() {
    if (!state || state.imageTesting || !state.imageAction) return;
    const current = state;
    const ticket = generation;
    current.imageTesting = true;
    current.imageTest = null;
    render();
    try {
      current.imageTest = await api("POST", modelPath() + "/image/test", {action: current.imageAction});
    } catch (error) {
      current.imageTest = {action: current.imageAction, registered: false, current: false, error: error.message || "注册检查失败。"};
    } finally {
      if (ticket === generation && state === current) { current.imageTesting = false; render(); }
    }
  }

  async function testStorage() {
    if (!state || state.storageTesting) return;
    const current = state;
    const ticket = generation;
    current.storageTesting = true;
    current.storageTest = null;
    render();
    try {
      const result = await api("POST", modelPath() + "/test/storage", {check: "sqlite"});
      if (ticket !== generation || state !== current) return;
      current.storageTest = {...result, status: result.status || "unknown",
        title: result.status === "ok" ? "SQLite 完整性检查通过" : "SQLite 完整性检查发现问题",
        message: result.status === "ok"
          ? "quick_check 与外键检查通过 · " + number(result.elapsed_ms) + " ms"
          : (Array.isArray(result.integrity) ? result.integrity.join(" · ") : "") +
            (result.foreign_key_issues ? " · 存在外键异常" : " · 检查未通过"),
        suggestion: result.status === "ok" ? "只读完整性检查通过，数据库页数未被更改。" : "保留数据库现状并检查宿主日志与外键异常样本。"};
    } catch (error) {
      if (ticket !== generation || state !== current) return;
      current.storageTest = {status: "failed", code: error.code || "model_storage_check_failed", title: "SQLite 完整性检查失败", message: error.message || "检查失败。",
        suggestion: "确认当前管理身份仍有效，并稍后重新运行只读检查。"};
    } finally {
      if (ticket === generation && state === current) { current.storageTesting = false; render(); }
    }
  }

  function updatePromptTask(result, reset) {
    const updated = result?.task;
    if (!updated || !updated.kind) return;
    const tasks = Array.isArray(state.modelStatus?.tasks) ? state.modelStatus.tasks : [];
    state.modelStatus = {...state.modelStatus, tasks: tasks.map(task => task.kind === updated.kind ? updated : task)};
    const task = promptTasks().find(item => item.kind === updated.kind);
    if (!task) return;
    state.promptSelectedKind = task.kind;
    state.promptDraft = task.prompt;
    state.promptInitial = task.prompt;
    state.promptEditToken = String(task.edit_token || "");
    state.promptInitialized = true;
    state.promptStale = false;
    state.promptOperationKey = "";
    state.promptOperationKind = "";
    state.promptMessage = reset ? "已恢复该任务的内置默认提示词。" : "提示词已保存。";
    state.promptMessageKind = "ok";
  }

  async function savePrompt(reset = false) {
    const task = promptSelectedTask();
    if (!task || state.promptSaving || !state.promptEditToken) return;
    const restoreDefault = !reset && state.promptDraft.trim() === "";
    if (!reset && (!promptDirty() || state.promptStale || state.promptDraft.length > PROMPT_LIMIT)) return;
    if (reset && !task.customized && !promptDirty()) return;
    if (restoreDefault && !task.customized && !promptDirty()) return;
    const current = state;
    const ticket = generation;
    const operationKey = promptOperationKey();
    current.promptSaving = true;
    current.promptMessage = reset || restoreDefault ? "正在恢复内置默认……" : "正在保存提示词……";
    current.promptMessageKind = "busy";
    render();
    try {
      const body = {kind: task.kind, operation_key: operationKey, edit_token: task.edit_token,
        changes: reset || restoreDefault ? {} : {prompt: current.promptDraft},
        reset: reset || restoreDefault ? ["prompt"] : []};
      const result = await api("POST", modelPath() + "/configure", body);
      if (ticket !== generation || state !== current) return;
      updatePromptTask(result, reset || restoreDefault);
    } catch (error) {
      if (ticket !== generation || state !== current) return;
      const known = Boolean(error.code);
      current.promptStale = error.code === "configuration_revision_conflict";
      current.promptMessageKind = current.promptStale ? "warn" : known ? "error" : "unknown";
      current.promptMessage = current.promptStale
        ? "保存时发现版本冲突，当前草稿已保留；请重新读取最新配置。"
        : known ? routeError(error.code) : "保存结果未知，草稿与操作键已保留；确认状态后可重试。";
    } finally {
      if (ticket === generation && state === current) { current.promptSaving = false; render(); }
    }
  }

  async function reloadPromptFromServer() {
    const selectedKind = state?.promptSelectedKind;
    if (!selectedKind || state.promptReloading || state.promptSaving) return;
    const current = state;
    const ticket = generation;
    current.promptReloading = true;
    current.promptMessage = "正在读取最新服务器配置……";
    current.promptMessageKind = "busy";
    render();
    try {
      const latest = await api("GET", modelPath());
      if (ticket !== generation || state !== current) return;
      const latestTask = Array.isArray(latest?.tasks) ? latest.tasks.find(item => item?.kind === selectedKind) : null;
      if (!latestTask) throw new Error("当前任务已从 V2 注册目录移除，请刷新维护页。" );
      const accepted = typeof window.confirm === "function"
        ? window.confirm("已读取最新任务配置。确认后会替换当前草稿，未保存内容将丢失。") : true;
      if (!accepted) {
        current.promptMessage = "已保留当前草稿。";
        current.promptMessageKind = "warn";
        return;
      }
      current.modelStatus = latest;
      current.promptSelectedKind = selectedKind;
      const task = promptTasks().find(item => item.kind === selectedKind);
      if (!task) throw new Error("当前任务已从 V2 注册目录移除，请刷新维护页。" );
      current.promptDraft = task.prompt;
      current.promptInitial = task.prompt;
      current.promptEditToken = String(task.edit_token || "");
      current.promptInitialized = true;
      current.promptStale = false;
      current.promptMessage = "已载入最新服务器配置。";
      current.promptMessageKind = "ok";
      current.promptOperationKey = "";
      current.promptOperationKind = "";
    } catch (error) {
      if (ticket !== generation || state !== current) return;
      current.promptMessage = error.code ? routeError(error.code) : (error.message || "读取最新配置失败，当前草稿已保留。" );
      current.promptMessageKind = error.code ? "error" : "unknown";
    } finally {
      if (ticket === generation && state === current) { current.promptReloading = false; render(); }
    }
  }

  function exportTokens() {
    if (!state?.data || typeof document === "undefined" || typeof URL === "undefined" || typeof URL.createObjectURL !== "function") return;
    const data = state.data;
    const stats = statsFor(data);
    const rows = [["类型", "日期或名称", "Token", "调用", "失败", "输入", "缓存命中", "缓存写入", "输出", "本地计价微美元", "平均延迟毫秒", "Provider / 任务"]];
    rows.push(["统计范围", state.period, stats.tokens, stats.calls, stats.failures, stats.input, stats.cached,
      stats.creation, stats.output, stats.cost, stats.latency ?? "", "当前角色账本"]);
    for (const item of dimensions(data, stats, "providers")) {
      rows.push(["Provider", item.key || "未知", item.tokens, item.calls, item.failures, item.input_tokens,
        item.cached_input_tokens, item.cache_creation_tokens, item.output_tokens, item.cost_microusd, item.avg_latency_ms ?? "", ""]);
    }
    for (const item of dimensions(data, stats, "tasks")) {
      rows.push(["任务", taskName(item.key), item.tokens, item.calls, item.failures, item.input_tokens,
        item.cached_input_tokens, item.cache_creation_tokens, item.output_tokens, item.cost_microusd, item.avg_latency_ms ?? "", item.key || ""]);
    }
    const history = Array.isArray(data.history) ? data.history : [];
    const periodWindow = data.windows?.[state.period];
    const selectedHistory = state.period === "date" ? history.filter(row => row.day === stats.day)
      : state.period === "today" ? history.filter(row => row.day === localDay(data.generated_at))
        : periodWindow ? history.filter(row => row.day >= periodWindow.start_day && row.day <= periodWindow.end_day)
          : state.period === "total" ? history : history.slice(-30);
    for (const item of selectedHistory) {
      rows.push(["每日", item.day || item.key, item.tokens, item.calls, item.failures, item.input_tokens,
        item.cached_input_tokens, item.cache_creation_tokens, item.output_tokens, item.cost_microusd, item.avg_latency_ms ?? "", ""]);
    }
    for (const item of matchingRecent(data)) {
      rows.push(["调用", item.at || "", item.tokens ?? "", 1, item.failure || "", item.input_tokens ?? "",
        item.cached_input_tokens ?? "", item.cache_creation_tokens ?? "", item.output_tokens ?? "", item.cost_microusd ?? "",
        item.latency_ms ?? "", taskName(item.kind) + " / " + (item.provider || "未知 Provider")]);
    }
    const csv = "\uFEFF" + rows.map(row => row.map(value => '"' + String(value ?? "").replace(/"/g, '""') + '"').join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "companion-v2-tokens-" + localDay(data.generated_at) + ".csv";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function click(event) {
    const target = event.target;
    const promptMode = target.closest("[data-prompt-mode]");
    if (promptMode && state) {
      state.promptMode = promptMode.dataset.promptMode === "customized" ? "customized" : "all";
      render();
      return;
    }
    const promptGroup = target.closest("[data-prompt-group]");
    if (promptGroup && state) {
      state.promptGroup = promptGroup.dataset.promptGroup || "all";
      render();
      return;
    }
    const promptTask = target.closest("[data-prompt-task]");
    if (promptTask && state) {
      if (promptTask.dataset.promptTask !== state.promptSelectedKind && promptDirty()) {
        state.promptMessage = "当前任务还有未保存更改，请先保存或恢复默认后再切换。";
        state.promptMessageKind = "warn";
        render();
        return;
      }
      state.promptSelectedKind = promptTask.dataset.promptTask || "";
      state.promptInitialized = false;
      state.promptMessage = "";
      state.promptMessageKind = "";
      render();
      return;
    }
    if (target.closest("[data-prompt-save]") && state) { void savePrompt(false); return; }
    if (target.closest("[data-prompt-reset]") && state) { void savePrompt(true); return; }
    if (target.closest("[data-prompt-discard]") && state) { reloadPromptFromServer(); return; }
    const period = target.closest("[data-period]");
    if (period && state) { state.period = period.dataset.period; state.selectedHour = ""; render(); return; }
    const source = target.closest("[data-token-source]");
    if (source && state) { state.tokenSource = source.dataset.tokenSource; render(); return; }
    const hour = target.closest("[data-select-hour]");
    if (hour && state) {
      state.period = "date";
      state.selectedDate = hour.dataset.selectDay;
      state.selectedHour = hour.dataset.selectHour;
      state.callFilter = "all";
      state.showAllCalls = true;
      render();
      return;
    }
    const day = target.closest("[data-select-day]");
    if (day && state) { state.period = "date"; state.selectedDate = day.dataset.selectDay; state.selectedHour = ""; render(); return; }
    const category = target.closest("[data-diagnostic-category]");
    if (category && state) {
      state.category = category.dataset.diagnosticCategory;
      if (["image_generation", "image_recognition"].includes(state.category)) {
        state.imageAction = state.category === "image_recognition" ? "recognize" : "generate";
        state.imageTest = null;
      }
      render();
      return;
    }
    const severity = target.closest("[data-diagnostic-severity]");
    if (severity && state) { state.severity = severity.dataset.diagnosticSeverity; render(); return; }
    const filter = target.closest("[data-set-call-filter]");
    if (filter && state) { state.callFilter = filter.dataset.setCallFilter; state.showAllCalls = true; render(); return; }
    if (target.closest("[data-clear-hour]") && state) { state.selectedHour = ""; render(); return; }
    const ranking = target.closest("[data-rank-kind]");
    if (ranking && state) { state.traceFilter = {kind: ranking.dataset.rankKind, key: ranking.dataset.rankKey}; state.callFilter = "all"; state.showAllCalls = true; render(); return; }
    if (target.closest("[data-clear-trace]") && state) { state.traceFilter = null; render(); return; }
    if (target.closest("[data-toggle-calls]") && state) { state.showAllCalls = !state.showAllCalls; render(); return; }
    if (target.closest("[data-export-tokens]")) { exportTokens(); return; }
    const focus = target.closest("[data-focus-panel]");
    if (focus && root) {
      const targetSelector = ({"task-audit": '[data-focus-target="task-audit"]', "test-zone": '[data-focus-target="test-zone"]',
        "budget-block": ".maint-budget-block", "storage-block": '[data-focus-target="storage-block"]',
        "identity-evidence": '[data-focus-target="identity-evidence"]',
        "delivery-evidence": '[data-focus-target="delivery-evidence"]', "proactive-evidence": '[data-focus-target="proactive-evidence"]',
        "debounce-evidence": '[data-focus-target="debounce-evidence"]',
        "prompt-evidence": '[data-focus-target="prompt-evidence"]', "cache-panel": ".maint-cache-panel"})[focus.dataset.focusPanel];
      root.querySelector(targetSelector)?.scrollIntoView?.({behavior: "smooth", block: "center"});
      return;
    }
    if (target.closest("[data-refresh]")) { void refresh(); return; }
    if (target.closest("[data-provider-probe]")) { void probe(); return; }
    if (target.closest("[data-voice-test]")) { void testVoice(); return; }
    if (target.closest("[data-image-test]")) void testImage();
    if (target.closest("[data-storage-test]")) void testStorage();
  }

  function change(event) {
    const target = event.target;
    if (!state) return;
    if (target.matches("[data-selected-date]")) {
      if (target.value) { state.selectedDate = target.value; state.period = "date"; state.selectedHour = ""; render(); }
    } else if (target.matches("[data-provider-select]")) { state.provider = target.value; state.test = null; }
    else if (target.matches("[data-voice-provider]")) { state.voiceProvider = target.value; state.voiceTest = null; }
    else if (target.matches("[data-voice-language]")) { state.voiceLanguage = target.value; state.voiceTest = null; }
    else if (target.matches("[data-image-action]")) { state.imageAction = target.value; state.imageTest = null; }
    else if (target.matches("[data-call-filter]")) { state.callFilter = target.value; state.showAllCalls = target.value !== "all"; render(); }
  }

  function input(event) {
    const target = event.target;
    if (!state) return;
    if (target.matches("[data-prompt-search]")) {
      const selection = [target.selectionStart, target.selectionEnd];
      state.promptQuery = target.value || "";
      render();
      const replacement = root?.querySelector?.("[data-prompt-search]");
      replacement?.focus?.();
      if (selection.every(Number.isInteger)) replacement?.setSelectionRange?.(...selection);
      return;
    }
    if (target.matches("[data-prompt-draft]")) {
      const selection = [target.selectionStart, target.selectionEnd];
      state.promptDraft = normalizePrompt(target.value);
      state.promptMessage = "";
      state.promptMessageKind = "";
      render();
      const replacement = root?.querySelector?.("[data-prompt-draft]");
      replacement?.focus?.();
      if (selection.every(Number.isInteger)) replacement?.setSelectionRange?.(...selection);
      return;
    }
    if (!target.matches("[data-call-search]")) return;
    const selection = [target.selectionStart, target.selectionEnd];
    state.callQuery = target.value || "";
    state.showAllCalls = Boolean(state.callQuery);
    render();
    const replacement = root?.querySelector?.("[data-call-search]");
    replacement?.focus?.();
    if (selection.every(Number.isInteger)) replacement?.setSelectionRange?.(...selection);
  }

  function unmount() {
    generation += 1;
    if (state?.refreshTimer) window.clearInterval?.(state.refreshTimer);
    if (root) {
      root.removeEventListener("click", click);
      root.removeEventListener("change", change);
      root.removeEventListener("input", input);
    }
    root = null;
    state = null;
  }

  function mount(element) {
    unmount();
    root = element;
    if (!root) return;
    generation += 1;
    state = {data: null, integrations: {}, error: "", loading: false, testing: false, voiceTesting: false, imageTesting: false,
      test: null, voiceTest: null, imageTest: null, provider: "", voiceProvider: "", imageAction: "", voiceLanguage: "zh",
      storageTest: null, storageTesting: false, tokenSource: "companion",
      period: "today", selectedDate: localDay(), selectedHour: "", category: "all", severity: "all", callFilter: "all",
      callQuery: "", traceFilter: null, showAllCalls: false, modelStatus: null,
      promptQuery: "", promptMode: "all", promptGroup: "all", promptSelectedKind: "",
      promptDraft: "", promptInitial: "", promptEditToken: "", promptInitialized: false,
      promptSaving: false, promptReloading: false, promptStale: false, promptMessage: "", promptMessageKind: "",
      promptOperationKey: "", promptOperationKind: ""};
    root.addEventListener("click", click);
    root.addEventListener("change", change);
    root.addEventListener("input", input);
    if (typeof window.setInterval === "function") {
      state.refreshTimer = window.setInterval(() => {
        if ((typeof document === "undefined" || document.visibilityState === "visible") && state && !state.loading) void refresh();
      }, 45000);
    }
    void refresh();
  }

  return {mount, unmount};
})();
