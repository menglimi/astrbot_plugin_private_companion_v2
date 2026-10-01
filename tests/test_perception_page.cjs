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
        「这两个扩展各自渲染到自己的挂载点」「设置按组保存、
        敏感字段不回显」「没有原生配置的扩展给出就绪说明」——
        这些在 vm 里桩掉宿主接口就能验，不必开浏览器。

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

function harness({providers} = {}) {
  const requests = [];
  const responses = providers || {
    screen: {available: true, settings: settings()},
    reality: {available: false, reason: '尚未安装'},
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
          Object.assign(target.values, payload.updates);
          for (const key of Object.keys(payload.updates)) {
            if (target.fields[key]?.sensitive) target.values[key] = '已设置';
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

test('every provider mounts into its own slot, installed or not', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  /* 关键：不能因为一个扩展没装就整块不渲染——用户要知道「没装」，
     而不是看到一片空白然后自己去猜哪里坏了。
     两个节点都被写了内容：一个出表单，一个出原因句。 */
  assert.match(root.html('screen'), /data-perception-form="screen"/);
  assert.equal(root.html('reality'), '<p class="memory-notice" role="status">尚未安装</p>');
});

test('a provider without native settings explains readiness instead of showing an empty form', async () => {
  const harnessed = harness({providers: {
    screen: {available: true, settings: {schema: 'companion.perception-settings.v1',
      mode: 'native_v2', read_only: true, runtime_ready: true, groups: [], fields: {}, values: {}}},
    reality: {available: false, reason: '尚未安装'},
  }});
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  assert.match(root.all(), /V2 原生截图已就绪/);
  assert.equal(await harnessed.requests.length, 0);
});

test('an installed provider renders a form per settings group', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  const markup = root.html('screen');
  /* 两个组各出一张表单。分组是后端的 schema 决定的，不是页面写死的——
     页面按 settings.groups 逐组渲染，组里只画这一组声明的字段。 */
  assert.match(markup, /data-perception-form="screen"/);
  assert.match(markup, /data-perception-group="runtime"/);
  assert.match(markup, /data-perception-group="vision"/);
  assert.match(markup, /保存本组/);
  /* 没装的扩展不该被塞进表单里的默认值骗到。 */
  assert.equal(root.html('reality'), '<p class="memory-notice" role="status">尚未安装</p>');
});

test('a sensitive value is never written back into the markup', async () => {
  const harnessed = harness();
  const root = rootStub();
  harnessed.page.mount(root);
  await drains();

  /* 令牌已经设置过。页面用 configured 表达「已设置」，输入框留空表示「可替换」，
     所以标记里不该出现任何真实值——把它回填等于密码明文躺在 DOM 里。 */
  const markup = root.html('screen');
  /* 密码框必须带着空 value 属性出现，并且旁边用一句「已设置，留空保持原值」
     说明它其实有值——两件事同时成立才叫「能改又不泄露」。 */
  assert.match(markup, /type="password" value=""/);
  assert.match(markup, /已设置，留空保持原值。/);
  assert.doesNotMatch(markup, /已设置"/, '标记里不该把可展示的值塞进属性');
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
  assert.match(app, /role="tablist" aria-label="感知配置分区"/);
  assert.match(app, /role="tabpanel" aria-labelledby="perception-tab-config-environment"/);
  assert.match(app, /\['ArrowRight','ArrowLeft','Home','End'\]/,
    '感知分区应支持方向键及 Home / End 键切换');
  assert.match(app, /String\(destination\)\.split\(':',2\)/,
    '看板来源应能同时定位配置分区与二级面板');
  for (const slot of ['modelWorkspace', 'contextImageWorkspace', 'perceptionOnlineQueryWorkspace',
    'perceptionRecallWorkspace', 'mihomeStatusWorkspace']) {
    assert.match(app, new RegExp(`id="${slot}"`), `${slot} 应由感知配置页提供真实挂载点`);
  }
  assert.match(app, /sectionIds:\['news','web','selflink'\]/,
    'V1 网络探索、资讯和外部事件关联配置应在感知页可编辑');
  const overview = fs.readFileSync(path.join(PAGE_ROOT, 'perception-overview.js'), 'utf8');
  assert.match(overview, /tab:"config-models:perception-detail-model-route"/);
  assert.match(overview, /tab:"config-recall:perception-detail-recalls"/);
  assert.match(overview, /tab:"config-environment:perception-detail-place"/);
  assert.match(overview, /tab:"config-screen:perception-detail-device-access"/);
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
  assert.doesNotMatch(app.slice(app.indexOf('function renderPerceptionOriginal'),
    app.indexOf('function renderDecisionOriginal')), /memberClueWorkspace|semanticLearningWorkspace|semanticExpressionWorkspace|reactionConfigWorkspace/);
  assert.match(learning, /semanticLearningWorkspace/);
  assert.match(expression, /reactionConfigWorkspace/);
  assert.match(expression, /semanticExpressionWorkspace/);
});
