import * as THREE from "../vendor/three.module.min.js";
import { createResidentRig } from "./home-room-resident-rig.source.js";
import { createPaperRig } from "./home-room-paper-rig.source.js";
import { isRoomPointFree, nearestRoomPoint, roomRoute, roomSegmentFree } from "./home-room-navigation.mjs";

// Appearance and animation consume a presentation intent, never a model task.
export function createRoomResident(scene, getWorld, changed) {
  const root = new THREE.Group(); scene.add(root); root.visible = false;
  let rig = null, appearanceKey = "", presentationKey = "", context = null, worldKey = "";
  let position = { x: .8, z: 2 }, route = [], goal = "idle", phase = "idle", rest = 4;
  let seating = 0, height = 1, radius = .25, desiredAngle = Math.PI, blocked = false, turn = 0;
  let world = null, checkIn = 0, salute = 0, speed = 0, viewer = null, statusKey = "";
  function rebuild(value) {
    const previousHeight = height;
    rig?.dispose(); height = value.height || 1; radius = .25 * height;
    root.scale.setScalar(height);
    rig = context?.presentation?.mode === "paper" ? createPaperRig(root, context.presentation.module) : createResidentRig(root, value);
    if (height !== previousHeight) worldKey = "";
  }
  function status() {
    return { phase, goal, blocked, facing: root.rotation.y, position: { ...position }, target: route.at(-1) || null,
      visible: root.visible, label: !context ? "正在读取角色" : blocked ? world?.desk ? "在空处等一会儿，书桌前暂时过不去" : "书桌收起了，先在小屋里歇一会儿" : phase === "seated" ? `在书桌旁翻看${context.work ? "「" + context.work.title + "」" : "手账"}` : phase === "walking" ? goal === "desk" ? "走向书桌" : "在屋里走走" : "在小屋里歇一会儿",
      ref: context?.work?.ref || null, appearance: appearanceKey ? JSON.parse(appearanceKey) : null,
      presentation: context?.presentation?.mode || "voxel", paperReady: rig?.ready ?? null, paperFailed: rig?.failed ?? false };
  }
  function notify() { const value = status(), key = JSON.stringify([value.phase, value.goal, value.blocked, value.label, value.visible]); if (key !== statusKey) { statusKey = key; changed?.(value); } }
  function plan() {
    if (!context || !world) return;
    blocked = false; route = [];
    // Room edits may put furniture over the old position. Relocate to the
    // closest valid floor cell before showing the resident again.
    if (!isRoomPointFree(position, world, radius)) {
      if (!(phase === "seated" && world.desk && worldKey)) position = nearestRoomPoint(position, world, radius);
      if (!position) { position = { x: .8, z: 2 }; root.visible = false; blocked = true; return; }
    }
    if (goal === "desk" && world.desk) {
      const approach = world.desk.approach, seat = world.desk.seat;
      // The short docking segment may enter its own chair, never other furniture.
      if (roomSegmentFree(approach, seat, world, radius, ["desk"])) {
        route = roomRoute(position, approach, world, radius);
        if (route.length) { route.push({ x: seat.x, z: seat.z, dock: true }); phase = "walking"; return; }
      }
      blocked = true;
    } else if (goal === "desk") blocked = true;
    phase = "idle"; rest = 12; seating = 0;
  }
  function syncWorld() {
    const next = getWorld(), signature = JSON.stringify(next);
    if (signature === worldKey) return;
    const seated = phase === "seated";
    world = next; worldKey = signature;
    if (seated) { phase = "idle"; position = nearestRoomPoint(position, world, radius) || position; }
    plan();
  }
  function setContext(value) {
    const previous = context, key = value ? JSON.stringify(value.appearance) : "";
    context = value;
    if (!value) { root.visible = false; route = []; phase = "idle"; goal = "idle"; worldKey = ""; salute = 0; speed = 0; viewer = null; seating = 0; notify(); return; }
    const nextPresentation = value.presentation?.mode === "paper" ? value.presentation.id : "voxel";
    if (key !== appearanceKey || nextPresentation !== presentationKey) { appearanceKey = key; presentationKey = nextPresentation; rebuild(value.appearance); }
    goal = value.work ? "desk" : "idle";
    const changedIntent = goal !== (previous?.work ? "desk" : "idle") || JSON.stringify(previous?.work?.ref) !== JSON.stringify(value.work?.ref);
    syncWorld();
    if (changedIntent) {
      if (phase === "seated") { position = world.desk?.approach || nearestRoomPoint(position, world, radius) || position; phase = "idle"; }
      plan();
    }
    root.visible = true; notify();
  }
  function tick(delta, { paused = false, reduced = false, viewer: nextViewer = null } = {}) {
    if (!context) return false;
    const visible = root.visible; root.visible = !paused;
    if (paused) return visible;
    // Follow active elapsed time on slower GPUs too; setActive resets the
    // parent clock, so time on a hidden page never advances the walk.
    const dt = Math.min(1, Math.max(0, delta)); checkIn -= dt;
    if (nextViewer) viewer = nextViewer;
    salute = reduced ? 0 : Math.max(0, salute - dt);
    let traveled = 0;
    if (checkIn <= 0) { syncWorld(); checkIn = .5; }
    if (blocked && !isRoomPointFree(position, world, radius)) root.visible = false;
    if (!root.visible) { notify(); return visible; }
    if (phase === "idle" && goal !== "desk" && !reduced) {
      rest -= dt;
      if (rest <= 0) {
        const candidates = [{ x: .8, z: 2.5 }, { x: 1.8, z: -.5 }, { x: -.6, z: .3 }, { x: 2.6, z: 3.6 }];
        const target = candidates[turn++ % candidates.length]; route = roomRoute(position, target, world, radius);
        if (route.length) phase = "walking"; else rest = 8;
      }
    }
    if (phase === "walking") {
      if (reduced) { position = { ...route.at(-1) }; route = []; }
      else {
        // Ease the actual displacement too, so feet do not stride in place
        // during starts, arrival or a click-to-greet pause.
        let remaining = 0, last = position;
        for (const point of route) { remaining += Math.hypot(point.x - last.x, point.z - last.z); last = point; }
        const targetSpeed = salute > .4 ? 0 : .85 * Math.min(1, .22 + remaining / .65);
        let step = targetSpeed * dt + (speed - targetSpeed) * (1 - Math.exp(-6 * dt)) / 6;
        speed = THREE.MathUtils.damp(speed, targetSpeed, 6, dt);
        while (route.length && step > 0) {
          const next = route[0], distance = Math.hypot(next.x - position.x, next.z - position.z);
          desiredAngle = Math.atan2(next.x - position.x, next.z - position.z);
          if (distance <= step) { position = { x: next.x, z: next.z }; route.shift(); step -= distance; traveled += distance; }
          else { position.x += (next.x - position.x) / distance * step; position.z += (next.z - position.z) / distance * step; traveled += step; step = 0; }
        }
      }
      if (!route.length) { phase = goal === "desk" && world.desk ? "seated" : "idle"; rest = 14; }
    }
    const sitting = phase === "seated", previousSeating = seating;
    if (phase !== "walking" || reduced) speed = 0;
    seating = reduced ? Number(sitting) : THREE.MathUtils.damp(seating, Number(sitting), 6, dt);
    if (sitting) desiredAngle = world.desk.angle;
    const toViewer = viewer ? Math.atan2(viewer.x - position.x, viewer.z - position.z) : desiredAngle;
    const face = salute > .4 && !sitting ? toViewer : desiredAngle;
    const turnAngle = Math.atan2(Math.sin(face - root.rotation.y), Math.cos(face - root.rotation.y));
    const rotation = turnAngle * (reduced ? 1 : 1 - Math.exp(-5 * dt));
    root.rotation.y += rotation;
    root.position.set(position.x, world.desk ? (world.desk.seat.y - .76 * height) * seating : 0, position.z);
    const gazeYaw = Math.atan2(Math.sin(toViewer - root.rotation.y), Math.cos(toViewer - root.rotation.y));
    const gazePitch = viewer ? -Math.atan2(viewer.y - (root.position.y + 1.55 * height), Math.hypot(viewer.x - position.x, viewer.z - position.z)) : 0;
    const posed = rig.pose(dt, { distance: traveled, speed: dt > 0 ? traveled / dt : speed, sitting: seating,
      attention: salute, gazeYaw, gazePitch: THREE.MathUtils.clamp(gazePitch, -.3, .3), turnRate: dt > 0 ? rotation / dt : 0, reduced, reading: Boolean(context.work) });
    notify();
    return visible !== root.visible || traveled > 0 || posed || previousSeating !== seating;
  }
  return {
    setContext, tick, getState: status, get meshes() { return rig?.meshes || []; },
    greet(target) { if (target) viewer = { x: target.x, y: target.y, z: target.z }; salute = 3.2; },
    dispose() { root.removeFromParent(); rig?.dispose(); },
  };
}
