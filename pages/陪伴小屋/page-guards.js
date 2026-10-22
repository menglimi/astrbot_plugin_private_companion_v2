"use strict";
/* 页面级"未保存改动"的注册点。
 *
 * 为什么需要它：离开页面时的守卫原本只问工作台内核（`CompanionWorkbench.dirtyEditors()`），
 * 于是房间布置、角色档案草稿、感知分段、模型配置、语义草稿、开始使用向导这些
 * 自带草稿的编辑面，换页时改动会被静默丢掉。
 *
 * 用法：模块导出 `isDirty()`，在 app.js 里注册一条带名字的检查；
 * `dirty()` 返回可直接进确认框的条目（title 用于提示文案）。
 */
window.CompanionPageGuards = (() => {
  const sources = new Map();

  /* 注册一条检查；返回注销函数。重复注册同名 id 会覆盖旧检查。 */
  function register(id, title, dirty) {
    if (typeof id !== "string" || !id || typeof dirty !== "function") return () => {};
    sources.set(id, { id, title: title || id, dirty });
    return () => {
      if (sources.get(id)?.dirty === dirty) sources.delete(id);
    };
  }

  /* 逐条求值；单条抛错不影响其他条目，也不阻断离开。 */
  function dirty() {
    const pending = [];
    for (const source of sources.values()) {
      try {
        if (source.dirty()) pending.push({ id: source.id, title: source.title, group: source.id });
      } catch (error) {
        console.warn("[陪伴小屋] 未保存检查失败", source.id, error);
      }
    }
    return pending;
  }

  return { register, dirty, get size() { return sources.size; } };
})();
