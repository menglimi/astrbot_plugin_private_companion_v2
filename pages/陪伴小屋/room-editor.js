'use strict';

// The room stays visible while its right-side status and agenda panel becomes the editor.
let roomEditorState = null;
let roomEditorSignature = '';

function editorOptions(items, selected) {
  return Object.entries(items).map(([id, value]) => `<option value="${escapeHTML(id)}" ${id === selected ? 'selected' : ''}>${escapeHTML(typeof value === 'string' ? value : value.label)}</option>`).join('');
}

function openRoomEditor() {
  if (arrangementDraft) return;
  if (!voxelController || $('.voxel-scene-failed')) {
    toast('请先重新加载体素小屋，再进入布置');
    return;
  }
  closeDetail();
  if (window.CompanionShell?.section) backHome();
  const side = $('#shellSide');
  if (!side) return;
  arrangementDraft = {
    role: layoutKey(), scene: state.scene,
    layout: voxelController.getLayout(),
    returnFocus: document.activeElement, returnFurniture: document.activeElement?.dataset?.locateFurniture,
  };
  const catalog = voxelController.getCatalog();
  side.innerHTML = `<section class="room-editor" id="roomEditor" aria-labelledby="roomEditorTitle">
    <header class="room-editor-header">
      <div><small>${roleName()}的小屋</small><h1 id="roomEditorTitle">布置房间</h1></div>
      <div class="room-editor-actions"><button class="button" data-room-cancel>取消</button><button class="button primary" data-room-save>保存布置</button></div>
    </header>
    <p class="room-editor-hint" data-room-hint role="status"></p>
    <aside class="room-editor-controls" aria-label="布置工具">
        <div class="room-editor-history"><button class="button small" data-room-undo disabled>${I('undo-2')}撤销</button><button class="button small" data-room-redo disabled>${I('redo-2')}重做</button><span>本次调整</span></div>
        <div class="room-editor-field"><label for="roomHouseStyle">房间风格</label><select id="roomHouseStyle" data-room-house>${editorOptions(catalog.houseStyles, 'classic')}</select><small data-room-materials></small></div>
        <div class="room-editor-divider"></div>
        <div class="room-editor-field"><label for="roomFurniture">选择家具 <span data-room-placement></span></label><select id="roomFurniture" data-room-furniture></select></div>
        <div class="room-editor-field"><label for="roomFurnitureStyle">家具外观</label><select id="roomFurnitureStyle" data-room-style>${editorOptions(catalog.styles, 'oak')}</select><small data-room-style-note></small></div>
        <div class="room-editor-field" data-room-model-field hidden><label for="roomFurnitureModel">家具款式</label><select id="roomFurnitureModel" data-room-model></select></div>
        <div class="room-editor-field" data-room-surface-field hidden><label for="roomFurnitureSurface">摆放位置</label><select id="roomFurnitureSurface" data-room-surface></select></div>
        <div class="room-editor-placement">
          <div><span class="room-editor-field-label">微调位置</span><div class="room-editor-nudge"><button data-room-nudge="up" aria-label="向前或向上移动家具">${I('arrow-up')}</button><button data-room-nudge="left" aria-label="向左移动家具">${I('arrow-left')}</button><span>${I('move')}</span><button data-room-nudge="right" aria-label="向右移动家具">${I('arrow-right')}</button><button data-room-nudge="down" aria-label="向后或向下移动家具">${I('arrow-down')}</button></div></div>
          <div class="room-editor-rotation" data-room-rotation><span class="room-editor-field-label">旋转方向</span><div><button class="button small" data-room-rotate="-90" aria-label="向左旋转 90 度">${I('rotate-ccw')}</button><button class="button small" data-room-rotate="90" aria-label="向右旋转 90 度">${I('rotate-cw')}</button></div><output data-room-angle></output></div>
        </div>
        <button class="button room-editor-store" data-room-store></button>
        <p class="room-editor-help">收纳只改变摆放，功能仍可从家具目录打开。</p>
        <div class="room-editor-divider"></div>
        <div class="room-editor-field"><label for="roomPreviewTime">预览时段</label><select id="roomPreviewTime" data-room-time>${sceneTimes.map(([id, label]) => `<option value="${id}" ${id === state.scene ? 'selected' : ''}>${label}</option>`).join('')}</select></div>
        <p class="room-editor-help">保存在当前浏览器；取消或 Esc 撤销本次调整。</p>
    </aside>
  </section>`;
  side.setAttribute('aria-label', '布置房间工作台');
  document.body.classList.add('room-editing');
  const canvas = $('.room-stage canvas');
  canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', '布置房间。点选或拖动家具，方向键微调，R 旋转，Ctrl 或 Command Z 撤销。');
  icons();
  voxelController.setEditing(true);
  voxelController.resize();
  canvas.focus({preventScroll: true});
}

function updateRoomEditor(editor) {
  if (!arrangementDraft || !$('#roomEditor') || !editor.editing) return;
  roomEditorState = editor;
  const signature = JSON.stringify([editor.id, editor.houseStyle, editor.item.style, editor.item.model, editor.item.surface, editor.item.rotation, editor.item.stored, editor.canUndo, editor.canRedo, editor.hint, editor.blocked]);
  if (signature === roomEditorSignature) return;
  roomEditorSignature = signature;
  const catalog = voxelController.getCatalog();
  const stored = new Set(voxelController.getState().storedFurniture);
  const choices = Object.fromEntries(Object.entries(catalog.furniture).filter(([id]) => {
    const entry = directory.find(item => item.station === id);
    return !entry?.cap || state.modules[entry.cap] !== 'removed';
  }).map(([id, label]) => [id, label.replace(/ · .+$/, '') + (stored.has(id) ? ' · 已收纳' : '')]));
  const picker = $('[data-room-furniture]');
  const choiceHTML = editorOptions(choices, editor.id);
  if (picker.innerHTML !== choiceHTML) picker.innerHTML = choiceHTML;
  picker.value = editor.id;
  $('[data-room-house]').value = editor.houseStyle;
  $('[data-room-materials]').textContent = catalog.houseStyles[editor.houseStyle]?.materials || '';
  $('[data-room-style]').value = editor.item.style;
  $('[data-room-style-note]').textContent = catalog.styleDetails[editor.item.style]?.note || '';
  const models = catalog.objectModels[editor.id] || {};
  $('[data-room-model-field]').hidden = Object.keys(models).length < 2;
  $('[data-room-model]').innerHTML = editorOptions(models, editor.item.model);
  const surfaces = models[editor.item.model]?.surfaces || ['floor'];
  $('[data-room-surface-field]').hidden = surfaces.length < 2;
  $('[data-room-surface]').innerHTML = editorOptions(Object.fromEntries(surfaces.map(id => [id, catalog.surfaces[id]])), editor.item.surface);
  $('[data-room-placement]').textContent = stored.has(editor.id) ? '已收纳' : '已摆放';
  $('[data-room-store]').innerHTML = I(stored.has(editor.id) ? 'package-open' : 'archive') + (stored.has(editor.id) ? '摆回房间' : '收纳这件家具');
  $('[data-room-rotation]').hidden = editor.item.surface !== 'floor';
  $('[data-room-angle]').textContent = `${Math.round(editor.item.rotation)}°`;
  $('[data-room-undo]').disabled = !editor.canUndo;
  $('[data-room-redo]').disabled = !editor.canRedo;
  $('[data-room-hint]').textContent = editor.hint;
  $('[data-room-hint]').classList.toggle('is-blocked', editor.blocked);
  icons();
}

function nudgeRoomFurniture(direction) {
  if (!roomEditorState || !voxelController) return;
  const item = roomEditorState.item;
  const step = .25;
  const patch = {};
  if (direction === 'left' || direction === 'right') {
    const axis = item.surface === 'left-wall' ? 'z' : 'x';
    patch[axis] = item[axis] + (direction === 'left' ? -step : step) * (axis === 'z' ? -1 : 1);
  } else {
    const axis = item.surface === 'floor' ? 'z' : 'y';
    patch[axis] = item[axis] + (direction === 'up' ? step : -step) * (axis === 'z' ? -1 : 1);
  }
  voxelController.updateFurniture(patch);
}

function finishRoomEditor(save) {
  if (!arrangementDraft) return;
  const draft = arrangementDraft;
  voxelController?.setEditing(false);
  if (save && voxelController) {
    const layout = voxelController.getLayout();
    // Capability removal is distinct from the user's choice to store furniture.
    for (const entry of directory.filter(item => item.cap && state.modules[item.cap] === 'removed' && item.station)) {
      if (!layout.items[entry.station]) continue;
      if (state.roomLayouts[draft.role]?.items?.[entry.station]?.stored) layout.items[entry.station].stored = true;
      else delete layout.items[entry.station].stored;
    }
    state.roomLayouts[draft.role] = layout;
    state.scene = draft.scene;
  } else {
    voxelController?.setLayout(draft.layout);
  }
  $('#roomEditor')?.remove();
  document.body.classList.remove('room-editing');
  arrangementDraft = null;
  roomEditorState = null;
  roomEditorSignature = '';
  const canvas = $('.room-stage canvas');
  if (canvas) {
    canvas.removeAttribute('tabindex');
    canvas.setAttribute('aria-label', '体素小屋。可拖动旋转、滚轮缩放，也可使用下方家具按钮浏览内容。');
  }
  syncEnvironment();
  voxelController?.resize();
  renderShellSide();
  updateFurnitureDirectory();
  if (draft.returnFocus?.isConnected) draft.returnFocus.focus({preventScroll: true});
  else if (draft.returnFurniture) $(`[data-locate-furniture="${draft.returnFurniture}"]`)?.focus({preventScroll: true});
  if (save) saved('房间布置已保存');
}

function handleRoomEditorClick(el) {
  if (!arrangementDraft) return false;
  if (el.hasAttribute('data-room-save')) finishRoomEditor(true);
  else if (el.hasAttribute('data-room-cancel')) finishRoomEditor(false);
  else if (el.hasAttribute('data-room-undo')) voxelController.undoEdit();
  else if (el.hasAttribute('data-room-redo')) voxelController.undoEdit(true);
  else if (el.hasAttribute('data-room-store')) voxelController.setFurnitureStored(!voxelController.getState().storedFurniture.includes(roomEditorState.id));
  else if (el.dataset.roomNudge) nudgeRoomFurniture(el.dataset.roomNudge);
  else if (el.dataset.roomRotate) voxelController.updateFurniture({rotation: roomEditorState.item.rotation + Number(el.dataset.roomRotate)});
  else return false;
  return true;
}

function handleRoomEditorChange(el) {
  if (!arrangementDraft) return false;
  if (el.hasAttribute('data-room-house')) voxelController.updateHouseStyle(el.value);
  else if (el.hasAttribute('data-room-furniture')) voxelController.selectFurniture(el.value);
  else if (el.hasAttribute('data-room-style')) voxelController.updateFurniture({style: el.value});
  else if (el.hasAttribute('data-room-model')) voxelController.updateFurniture({model: el.value});
  else if (el.hasAttribute('data-room-surface')) voxelController.updateFurniture({surface: el.value});
  else if (el.hasAttribute('data-room-time')) {
    arrangementDraft.scene = el.value;
    syncEnvironment({...state, scene: el.value});
  } else return false;
  return true;
}

function handleRoomEditorKey(event) {
  if (!arrangementDraft) return false;
  if (event.key === 'Escape') {
    event.preventDefault();
    finishRoomEditor(false);
    return true;
  }
  if (event.target.matches('input,textarea,select,[contenteditable="true"]')) return true;
  const key = event.key.toLowerCase();
  if ((event.ctrlKey || event.metaKey) && key === 'z') {
    event.preventDefault();voxelController.undoEdit(event.shiftKey);
  } else if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
    event.preventDefault();nudgeRoomFurniture(event.key.slice(5).toLowerCase());
  } else if (key === 'r' && roomEditorState?.item.surface === 'floor') {
    event.preventDefault();voxelController.updateFurniture({rotation: roomEditorState.item.rotation + 90});
  }
  return true;
}
