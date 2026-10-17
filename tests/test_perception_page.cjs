/* 感知页。

   这一份原先是一个 Playwright 端到端脚本：起一个静态服务器、开无头 Chromium、
   点导航、量移动端宽度、截图。它有三个问题，所以改写成了纯 vm 测试：

     1. **它跑不起来**。这个仓库里没有 playwright，沙箱也装不上（没有网络），
        所以那份脚本事实上从来没被执行过——一份永远不跑的测试等于没有测试，
        而它拦不住任何回归。
     2. **它断言的东西已经不存在了**。它取 `#main .console-section-code` 里
        的 A1/B2/C3 编号当断言目标，但那些编号正是这一轮要去掉的脚手架；
   它数 `#mainNav .rail-link` 与 `#navigationDialog .navigation-link`，
       那两个 id 现在都不在页面里。
     3. **它需要的是渲染结果，而不是浏览器**。真正值得守住的规矩是
        「Screen 由 V2 原生工作区承载」「感知页只维护 Reality 提供方设置、
        设置按组保存且敏感字段不回显」——这些在 vm 里桩掉宿主接口就能验，
        不必开浏览器。

   导航结构的静态检查仍留着（它过去是这份脚本的一部分），但改成读源码：
   分组、条目数与 href 形状都是代码事实，读一次文件就能比对。
*/
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const PAGE_ROOT = path.resolve(__dirname, '../pages/陪伴小屋');
const source = fs.readFileSync(path.join(PAGE_ROOT, 'perception-page.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const drains = async (times = 10) => { for (let index = 0; index < times; index += 1) await flush(); };

function settings(overrides = {}) {
  return {
    schema: 'companion.perception-settings.v1', updated_at: null,
    groups: [
      {id: 'runtime', owner: 'companion', title: '运行', description: '', fields: ['enabled']},
      {id: 'vision', owner: 'companion', title: '视觉', description: '', fields: ['remote_auth_token']},
    ],
    fields: {
      enabled: {description: '启用屏幕', type: 'bool'},
      /* 敏感字段：读过一次之后输入框必须留空，否则密码会以明文躺在 DOM 里。 */
      remote_auth_token: {description: '远程令牌', type: 'string', sensitive: true, configured: true},
    },
    values: {enabled: false, remote_auth_token: '已设置'},
    ...overrides,
  };
}

function realitySettings() {
  return {
    global: {enabled: true, vision_provider_id: "vision", timezone: "Asia/Shanghai"},
    camera: {camera_enabled: false, camera_index: 0, min_interval_seconds: 10,
      capture_timeout_seconds: 2, analysis_timeout_seconds: 5, proactive_curiosity_enabled: false,
      proactive_min_tier: 1, proactive_max_daily: 0, proactive_cooldown_minutes: 60},
    mobile: {enabled: false, host: "127.0.0.1", port: 8765, public_base_url: "", allowed_user_id: "",
      session_ttl_hours: 24, location_ttl_seconds: 600, amap_reverse_geocode_enabled: false,
      amap_api_key: "secret-amap-token", amap_cache_ttl_seconds: 3600, amap_request_timeout_seconds: 5,
      telemetry_enabled: false, telemetry_ttl_seconds: 600, activity_enabled: false,
      activity_ttl_seconds: 600, screen_upload_enabled: false, pairing_token: "secret-pairing-token"},
    health: {enabled: false, ttl_seconds: 3600},
    secrets: {amap_api_key_configured: true, pairing_token_configured: true},
  };
}

function harness({providers} = {}) {
  const requests = [];
  const responses = providers || {
    screen: {available: true, settings: settings()},
    reality: {available: true, settings: realitySettings()},
  };
  const window = {
    /* unwrap 要真的把信封拆开：后端给的是 {status, data}，页面拿到的必须是 data。
       桩成恒等函数的话，页面会在信封上找 providers，永远读不到——那正是
       「配置暂不可读取」这句兜底话术的来路。 */
    CompanionProduct: {hosted: () => true, scopeKey: () => 'role-1',
      unwrap: response => (response?.data ?? response),
      /* 页面取桥先问 bridgeNow()，没有再 await bridgeFor()。 */
      bridgeNow: () => window.AstrBotPluginPage,
      bridgeFor: () => ({then: resolve => resolve(window.AstrBotPluginPage)})},
    AstrBotPluginPage: {
      apiGet: () => new Promise(resolve => {
        queueMicrotask(() => resolve({status: 'ok', data: {providers: responses}}));
      }),
      apiPost: (route, payload) => new Promise(resolve => {
        const entry = {method: 'POST', route, payload, resolve};
        requests.push(entry);
        const target = responses[payload.provider]?.settings;
        if (target && payload.updates) {
          const section = target[payload.section] || target.values;
          Object.assign(section, payload.updates);
          for (const key of Object.keys(payload.updates)) {
            if (target.fields?.[key]?.sensitive) target.values[key] = '已设置';
          }
        }
        queueMicrotask(() => resolve({status: 'ok', data: {provider: payload.provider,
                                                           settings: target}}));
      }),
    },
    lucide: {createIcons() {}},
    document: {querySelector: () => null},
  };
  vm.runInNewContext(source, {window, AbortController, Promise, Object, JSON, Array, String,
    Number, Boolean, Set, Map, RegExp, Error, console});
  return {page: window.CompanionPerceptionPage, window, requests};
}

/* 挂载点替身。
 *
 * 要点：这一页**只往扩展节点里写**，根节点自己始终是空的。
 * 所以断言要看节点，看根节点只会看到一片空白，然后把「页面没渲染」误判成失败。
 * 节点由测试显式声明——页面只认识 data-perception-provider，不会自己造节点。
 */
function rootStub(ids = ['screen', 'reality']) {
  const handlers = {};
  const nodes = new Map();
  for (const id of ids) {
    nodes.set(id, {
      id, dataset: {perceptionProvider: id}, innerHTML: '',
      querySelectorAll: () => [], querySelector: () => null,
    });
  }
  return {
    /* current() 会读 root.isConnected 判断这一份渲染还算不算数；
       替身不连在任何文档上，所以显式声明它是活的。 */
    isConnected: true,
    /* 根节点没有内容，这里给它一个只写不读的空位，页面写进来也当没有。 */
    innerHTML: '',
    addEventListener(type, handler) { handlers[type] = handler; },
    dispatch(type, event) { handlers[type]?.(event); },
    querySelector(selector) {
      const match = /\[data-perception-provider="([^"]+)"\]/.exec(selector);
      const node = match ? nodes.get(match[1]) : null;
      if (!node) return null;
      const group = /\[data-perception-group="([^"]+)"\]/.exec(selector);
      return group ? Object.assign(Object.create(node), {groupId: group[1]}) : node;
    },
    querySelectorAll: () => [],
    contains: () => true,
    /* 取出某个扩展节点里最终渲染出来的东西。 */
    html(id) { return nodes.get(id)?.innerHTML || ''; },
    /* 一次挂载后全部渲染结果，方便做「不该出现」的断言。 */
    all() { return [...nodes.values()].map(node => node.innerHTML).join('\n'); },
  };
}

test('the V2 perception page mounts Reality only and does not render legacy Screen settings', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  assert.equal(root.html('screen'), '');
  assert.match(root.html('reality'), /data-perception-form="reality"/);
  assert.doesNotMatch(root.html('reality'), /启用屏幕|remote_auth_token/);
  assert.equal(harnessed.requests.length, 0);
});

test('legacy Screen-shaped data is ignored while the native Screen workspaces remain wired', async () => {
  const harnessed = harness({providers: {
    screen: {available: true, settings: {schema: 'companion.perception-settings.v1',
      mode: 'native_v2', read_only: true, runtime_ready: true, groups: [], fields: {}, values: {}}},
    reality: {available: false, reason: '尚未安装'},
  }});
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  assert.equal(root.html('screen'), '');
  assert.equal(root.html('reality'), '<p class="memory-notice" role="status">尚未安装</p>');
  assert.equal(harnessed.requests.length, 0);
  const app = fs.readFileSync(path.join(PAGE_ROOT, 'app.js'), 'utf8');
  assert.match(app, /configEditors\('screenConfigWorkspace'/);
  assert.match(app, /data-screen-access/);
  assert.doesNotMatch(source, /astrbot_plugin_screen_companion/);
});

test('Reality settings render in their own configuration sections', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  const markup = root.html('reality');
  for (const section of ['global', 'camera', 'mobile', 'health']) {
    assert.match(markup, new RegExp(`data-perception-section="${section}"`));
  }
  assert.match(markup, /保存本组/);
  assert.equal(root.html('screen'), '');
});

test('saving a Reality field submits only the changed value to the perception route', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  const input = {dataset:{perceptionField:'camera_enabled'}, type:'checkbox', checked:true};
  const status = {textContent:''};
  const button = {disabled:false};
  const form = {
    dataset:{perceptionForm:'reality', perceptionSection:'camera', perceptionGroup:'camera'},
    reportValidity:() => true,
    querySelectorAll:() => [input],
    querySelector(selector) {
      return selector === '[role=status]' ? status : button;
    },
  };

  root.dispatch('submit', {target:{closest:() => form}, preventDefault() {}});
  await drains();

  assert.equal(harnessed.requests.length, 1);
  assert.equal(harnessed.requests[0].route, 'perception');
  assert.equal(JSON.stringify(harnessed.requests[0].payload), JSON.stringify({
    provider:'reality', section:'camera', updates:{camera_enabled:true},
  }));
  harnessed.page.unmount();
});

test('Reality secrets and legacy Screen values never enter the markup', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  const markup = root.html('reality');
  assert.match(markup, /type="password" value=""/);
  assert.match(markup, /已设置，留空保持原值。/);
  assert.doesNotMatch(markup, /secret-amap-token|secret-pairing-token|remote_auth_token/);
  assert.equal(root.html('screen'), '');
});

test('the current navigation keeps perception reachable and its secondary panels wired', () => {
  const app = fs.readFileSync(path.join(PAGE_ROOT, 'app.js'), 'utf8');
  const groups = app.match(/const navGroups = \[[\s\S]*?\n\];/);
  assert.ok(groups, 'navGroups 应当是一段可读的常量');

  /* 顶层导航按小屋、塑造角色、互动能力、连接与运行分组。 */
  const titles = [...groups[0].matchAll(/\['(小屋|塑造角色|互动能力|连接与运行)',/g)].map(m => m[1]);
  assert.deepEqual(titles, ['小屋', '塑造角色', '互动能力', '连接与运行']);

  /* 每一条都是 #route/tab 形状的相对锚点——绝对路径会让前缀叠两次、整族 404。 */
  const hrefs = [...app.matchAll(/navHref\(([^)]*)\)/g)];
  assert.ok(hrefs.length > 0, '导航应当通过 navHref 生成链接');
  assert.doesNotMatch(app, /navHref\([^)]*"\/astrbot_plugin/,
    'navHref 的入参必须是插件相对路径');
  assert.match(app, /class="perception-config-nav" role="tablist" aria-label="感知设置"/,
    '感知配置按设计提供四个正式子页签');
  assert.equal((app.match(/role="tab" aria-selected="false" aria-controls="perception-page-/g)||[]).length,4,
    '感知配置应提供四个可切换子页');
  assert.match(app, /id="perception-page-environment" role="tabpanel"/);
  assert.match(app, /id="perception-page-models" role="tabpanel"/);
  assert.match(app, /id="perception-page-reality" role="tabpanel"/);
  assert.match(app, /id="perception-page-external" role="tabpanel"/);
  assert.match(app, /String\(destination\)\.split\(':',2\)/,
    '看板来源应能同时定位配置分区与二级面板');
  for (const slot of ['modelWorkspace', 'contextImageWorkspace', 'perceptionOnlineQueryWorkspace',
    'perceptionRecallWorkspace', 'mihomeStatusWorkspace']) {
    assert.match(app, new RegExp(`id="${slot}"`), `${slot} 应由感知配置页提供真实挂载点`);
  }
  assert.match(app, /sectionIds:\['news','web','selflink'\]/,
    'V1 网络探索、资讯和外部事件关联配置应在感知页可编辑');
  const overview = fs.readFileSync(path.join(PAGE_ROOT, 'perception-overview.js'), 'utf8');
  /* 每条通道的跳线目标必须还在源头存在。这些值已被抽成变量复用，
     所以按目标值本身校验，而不是按它是字面量还是变量声明校验。 */
  for (const target of ['config-models:perception-detail-model-route', 'config-recall:perception-detail-recalls',
    'config-environment:perception-detail-place', 'config-screen:perception-detail-device-access']) {
    assert.match(overview, new RegExp(target), `感知明细应仍能定位到 ${target}`);
  }
});

test('related configuration stays in its intended relationship, learning and expression pages', () => {
  const app = fs.readFileSync(path.join(PAGE_ROOT, 'app.js'), 'utf8');
  const identity = app.slice(app.indexOf('function renderIdentityPageOriginal'),
    app.indexOf('function renderContactPageOriginal'));
  const learning = app.slice(app.indexOf('function renderLearningPage'),
    app.indexOf('function renderMaintenancePage(){'));
  const expression = app.slice(app.indexOf('function renderExpressionOriginal'),
    app.indexOf('const SELF_PROFILE_SECTIONS'));
  assert.match(identity, /memberClueWorkspace/);
  assert.match(identity, /identity-network-settings/);
  assert.ok(identity.indexOf('personConfigWorkspace') < identity.indexOf('memberClueWorkspace'));
  assert.ok(identity.indexOf('memberClueWorkspace') < identity.indexOf('renderIdentity()'));
  assert.doesNotMatch(identity, /identity-person|identity-directory/);
  assert.doesNotMatch(app.slice(app.indexOf('function renderPerceptionOriginal'),
    app.indexOf('function renderDecisionOriginal')), /memberClueWorkspace|semanticLearningWorkspace|semanticExpressionWorkspace|reactionConfigWorkspace/);
  assert.match(learning, /semanticLearningWorkspace/);
  assert.match(expression, /reactionConfigWorkspace/);
  assert.match(expression, /semanticExpressionWorkspace/);
});
