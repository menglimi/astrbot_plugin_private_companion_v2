import * as THREE from "../vendor/three.module.min.js";

const clamp = THREE.MathUtils.clamp;
const ease = (a, b, t) => THREE.MathUtils.smoothstep(t, a, b);
const pulse = (t, length, enter = .35, leave = .6) => ease(0, enter, t) * (1 - ease(length - leave, length, t));

// A presentation rig only: glances and gestures never become life records.
export function createResidentRig(root, appearance) {
  const geometry = new THREE.BoxGeometry(1, 1, 1), materials = [], meshes = [];
  const tint = (color, toward, amount) => new THREE.Color(color).lerp(new THREE.Color(toward), amount);
  const material = color => { const m = new THREE.MeshStandardMaterial({ color, roughness: .86 }); materials.push(m); return m; };
  const skin = material(appearance.skin), blush = material(tint(appearance.skin, "#d97778", .28));
  const hair = material(appearance.hair), hairLight = material(tint(appearance.hair, "#e6c49a", .17));
  const top = material(appearance.top), trim = material(tint(appearance.top, "#263941", .2));
  const bottom = material(appearance.bottom), seam = material(tint(appearance.bottom, "#e9dfcf", .14));
  const dark = material("#30323b"), iris = material("#302a30"), white = material("#fff9e9");
  function box(parent, xyz, size, mat) {
    const mesh = new THREE.Mesh(geometry, mat); mesh.position.set(...xyz); mesh.scale.set(...size);
    mesh.castShadow = true; mesh.receiveShadow = true; mesh.userData.station = "resident";
    parent.add(mesh); meshes.push(mesh); return mesh;
  }
  function joint(parent, name, xyz) { const g = new THREE.Group(); g.name = name; g.position.set(...xyz); parent.add(g); return g; }
  const hips = joint(root, "hips", [0, .76, 0]);
  box(hips, [0, .065, 0], [.40, .19, .28], bottom);
  const body = joint(hips, "chest", [0, .12, 0]);
  box(body, [0, .22, 0], [.44, .43, .30], top);
  box(body, [0, .40, -.005], [.39, .10, .28], top);
  box(body, [0, .025, .002], [.46, .07, .32], trim);
  box(body, [0, .45, .018], [.19, .08, .21], white);
  box(body, [0, .49, 0], [.15, .10, .17], skin);
  box(body, [.115, .255, .157], [.11, .10, .018], trim);
  box(body, [.115, .30, .171], [.12, .022, .025], white);
  const head = joint(body, "head", [0, .58, 0]);
  // Stepped cheek/jaw/crown silhouettes keep the room's voxel language without
  // turning the entire head or hairstyle into a single rectangular slab.
  box(head, [0, .11, 0], [.55, .50, .46], skin);
  box(head, [0, .105, .015], [.61, .36, .46], skin);
  box(head, [0, -.15, .015], [.43, .075, .40], skin);
  box(head, [0, .375, -.025], [.62, .10, .51], hair);
  box(head, [-.025, .443, -.04], [.46, .06, .40], hair);
  box(head, [0, .16, -.234], [.59, .40, .10], hair);
  const locks = [], eyes = [], pupils = [], brows = [], smile = [];
  const lock = (xyz, size, lean, mat = hair) => {
    const g = joint(head, "hair-lock", xyz); g.userData.lean = lean; locks.push(g);
    box(g, [0, -size[1] / 2, 0], size, mat); return g;
  };
  lock([-.215, .345, .227], [.18, .18, .09], -.14);
  lock([-.06, .38, .244], [.15, .12, .075], -.19, hairLight);
  lock([.075, .365, .24], [.12, .105, .07], -.12);
  lock([.225, .34, .18], [.12, .23, .17], .12);
  for (const side of [-1, 1]) {
    box(head, [side * .32, .05, -.002], [.09, .12, .12], skin);
    box(head, [side * .344, .05, .047], [.025, .06, .03], blush);
    lock([side * .286, .30, -.032], [.095, .29, .35], side * .035);
    const eye = joint(head, "eye", [side * .124, .105, .253]); eyes.push(eye);
    box(eye, [0, 0, 0], [.11, .12, .018], white);
    const pupil = joint(eye, "pupil", [0, 0, .014]); pupils.push(pupil);
    box(pupil, [0, -.003, 0], [.063, .088, .02], iris);
    box(pupil, [-.014, .025, .013], [.022, .026, .01], white);
    box(eye, [0, .065, .004], [.115, .018, .02], hair);
    const brow = joint(head, "brow", [side * .125, .227, .256]); brows.push(brow);
    box(brow, [0, 0, 0], [.106, .025, .021], hair);
    box(head, [side * .212, -.032, .253], [.077, .035, .014], blush);
    const corner = box(head, [side * .045, -.092, .251], [.018, .018, .017], iris); smile.push(corner);
  }
  box(head, [0, .013, .263], [.046, .048, .04], skin);
  box(head, [0, -.105, .25], [.078, .018, .018], iris);
  if (appearance.hair_style !== "short") {
    const long = appearance.hair_style === "long";
    for (const side of [-1, 1]) {
      lock([side * .285, .12, -.10], [.14, long ? .70 : .35, .28], side * -.025);
      lock([side * .19, .07, -.262], [.23, long ? .73 : .31, .13], side * .04);
    }
  }
  if (appearance.accessory === "glasses") {
    for (const side of [-1, 1]) {
      for (const y of [.02, .195]) box(head, [side * .133, y, .289], [.226, .022, .025], dark);
      for (const x of [.031, .235]) box(head, [side * x, .108, .289], [.022, .178, .025], dark);
      box(head, [side * .285, .158, .115], [.025, .025, .34], dark);
    }
    box(head, [0, .13, .289], [.065, .022, .025], dark);
  }
  const arms = [], elbows = [], hands = [], legs = [], knees = [], ankles = [];
  for (const side of [-1, 1]) {
    const arm = joint(body, "shoulder", [side * .29, .38, 0]); arms.push(arm);
    box(arm, [0, -.105, 0], [.17, .25, .23], top);
    const elbow = joint(arm, "elbow", [0, -.23, 0]); elbows.push(elbow);
    box(elbow, [0, -.095, 0], [.145, .21, .18], top);
    box(elbow, [0, -.19, 0], [.15, .06, .185], trim);
    const hand = joint(elbow, "hand", [0, -.245, .006]); hands.push(hand);
    box(hand, [0, 0, 0], [.13, .13, .155], skin);
    box(hand, [-side * .064, .015, .029], [.045, .075, .08], skin);
    const leg = joint(hips, "hip", [side * .125, 0, 0]); legs.push(leg);
    box(leg, [0, -.17, 0], [.175, .35, .235], bottom);
    const knee = joint(leg, "knee", [0, -.37, 0]); knees.push(knee);
    box(knee, [0, -.135, 0], [.155, .29, .215], bottom);
    box(knee, [0, -.27, 0], [.165, .04, .225], seam);
    const ankle = joint(knee, "ankle", [0, -.33, 0]); ankles.push(ankle);
    box(ankle, [0, .005, .05], [.20, .11, .31], dark);
    box(ankle, [0, -.045, .056], [.21, .032, .32], white);
    box(ankle, [0, .064, .11], [.12, .015, .07], white);
  }

  let age = 0, stride = 0, motion = 0, blinkAt = 2.1, blinkStart = -10, glanceAt = 1.3;
  let lookYaw = 0, lookPitch = 0, headYaw = 0, headPitch = 0, bodyYaw = 0, gestureAt = 6.5;
  let gestureStart = -20, gestureKind = 0, seed = 37, lastReduced = false;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  // Solve the two leg joints to a floor-relative ankle, keeping the sole flat.
  function footPose(index, z, y, hipY, sitting) {
    const a = .37, b = .33, down = hipY - y;
    const length = clamp(Math.hypot(down, z), .08, a + b - .001);
    const knee = Math.acos(clamp((length * length - a * a - b * b) / (2 * a * b), -1, 1));
    const hip = Math.atan2(-z, down) - Math.atan2(b * Math.sin(knee), a + b * Math.cos(knee));
    legs[index].rotation.x = THREE.MathUtils.lerp(hip, -Math.PI / 2, sitting);
    knees[index].rotation.x = THREE.MathUtils.lerp(knee, Math.PI / 2, sitting);
    ankles[index].rotation.x = -(legs[index].rotation.x + knees[index].rotation.x);
  }
  function pose(dt, { distance = 0, speed = 0, sitting = 0, attention = 0, gazeYaw = 0, gazePitch = 0, turnRate = 0, reduced = false } = {}) {
    if (!reduced) age += dt;
    stride += distance / (appearance.height || 1) * Math.PI * 2;
    const damp = (a, b, rate) => reduced ? b : THREE.MathUtils.damp(a, b, rate, dt);
    motion = reduced ? 0 : damp(motion, clamp(speed / .85, 0, 1), 9);
    if (!reduced && age >= blinkAt) { blinkStart = age; blinkAt = age + 2.6 + random() * 3.6; }
    if (!reduced && age >= glanceAt) {
      lookYaw = (random() - .5) * .85; lookPitch = (random() - .5) * .16;
      glanceAt = age + 2.4 + random() * 3.8;
    }
    if (!reduced && age >= gestureAt) {
      gestureStart = age; gestureKind = (gestureKind + 1) % 3; gestureAt = age + 7 + random() * 5;
    }
    const gestureTime = age - gestureStart;
    const gesture = reduced ? 0 : pulse(gestureTime, 3.6, .8, 1) * (1 - motion);
    const greetTime = 3.2 - attention;
    const greeting = reduced || attention <= 0 ? 0 : pulse(greetTime, 3.2, .3, .75);
    const wave = greeting * ease(.12, .48, greetTime);
    const breathing = reduced ? 0 : Math.sin(age * 2.15) * .006;
    const weight = reduced ? 0 : Math.sin(age * .68) * .018 * (1 - motion) * (1 - sitting);
    const reading = sitting * (1 - greeting);
    const ponder = reading * gesture * Number(gestureKind === 1);
    const adjust = reading * gesture * Number(gestureKind === 2);
    const stretch = (1 - sitting) * gesture * Number(gestureKind === 0) * (1 - greeting);
    const gaze = reduced ? 0 : greeting;
    bodyYaw = damp(bodyYaw, clamp(gazeYaw * .45, -.72, .72) * gaze + Math.sin(stride) * .045 * motion, 5);
    const headTarget = reduced ? 0 : THREE.MathUtils.lerp(lookYaw * (1 - motion * .65), clamp(gazeYaw - bodyYaw, -1.15, 1.15), gaze);
    headYaw = damp(headYaw, headTarget, 5);
    headPitch = damp(headPitch, reduced ? .12 * sitting : (.16 + lookPitch) * reading - ponder * .13 + gazePitch * gaze + lookPitch * (1 - sitting) * (1 - gaze), 5);
    hips.position.set(weight, .76 - .048 * motion * (1 - sitting) + Math.cos(stride * 2) * .01 * motion * (1 - sitting), .09 * sitting);
    body.position.y = .12 + breathing;
    body.rotation.set(.075 * motion + .14 * reading - .08 * stretch, bodyYaw, -weight * 1.3 + Math.sin(stride) * .025 * motion - clamp(turnRate, -2, 2) * .025 * motion);
    body.scale.y = 1 + breathing * .65;
    head.rotation.set(headPitch, headYaw, (reduced ? 0 : Math.sin(age * .71) * .025) + .095 * greeting - .075 * ponder);
    eyes.forEach((eye, index) => {
      const t = age - blinkStart - index * .012;
      const blink = reduced || t < 0 || t > .19 ? 0 : Math.sin(t / .19 * Math.PI);
      eye.scale.y = Math.max(.07, 1 - blink * .97 - greeting * .12);
      pupils[index].position.x = reduced ? 0 : clamp(headTarget - headYaw, -.6, .6) * .034 + headYaw * .014;
      pupils[index].position.y = reduced ? 0 : -headPitch * .04;
      brows[index].rotation.z = (index ? -1 : 1) * (.035 + greeting * .13 + ponder * .1);
      brows[index].position.y = .227 + greeting * .018;
      smile[index].position.y = -.09 + greeting * .013;
    });
    for (let i = 0; i < 2; i++) {
      const side = i ? 1 : -1, cycle = ((stride / (Math.PI * 2) + i * .5) % 1 + 1) % 1;
      const stance = cycle < .6, flight = (cycle - .6) / .4;
      const footZ = stance ? .30 - cycle / .6 * .60 : -.30 + ease(0, 1, flight) * .60;
      const footY = stance ? 0 : Math.sin(flight * Math.PI) * .145;
      footPose(i, footZ * motion + side * .017 * (1 - motion), .061 + footY * motion, hips.position.y, sitting);
      legs[i].rotation.z = weight * 1.3 * (1 - sitting);
      const swing = Math.sin(stride + i * Math.PI + .25) * motion;
      const restArm = -1.37 + ((appearance.height || 1) - 1) * .9;
      arms[i].rotation.set(swing * .48 * (1 - sitting) + restArm * reading - stretch * 1.15, -side * .07 * reading, side * (.07 + .06 * motion + .45 * stretch));
      elbows[i].rotation.set(-.12 - Math.max(0, -swing) * .35 - .55 * reading - stretch * .55, 0, 0);
      hands[i].rotation.set(-.08 * reading, 0, 0);
    }
    // A reading pause and hand reposition are offset from the head/eyes.
    arms[0].rotation.x += ponder * .12; elbows[0].rotation.x -= ponder * .72;
    arms[1].rotation.y -= adjust * .30; hands[1].rotation.z += adjust * .12;
    arms[1].rotation.x = THREE.MathUtils.lerp(arms[1].rotation.x, -.35, wave);
    arms[1].rotation.z = THREE.MathUtils.lerp(arms[1].rotation.z, 1.05, wave);
    elbows[1].rotation.z = wave * (1.35 + Math.sin(greetTime * 13) * .20);
    elbows[1].rotation.x = THREE.MathUtils.lerp(elbows[1].rotation.x, -.3, wave);
    hands[1].rotation.z += wave * Math.sin(greetTime * 13 - .45) * .20;
    locks.forEach((lock, i) => {
      lock.rotation.z = lock.userData.lean + (reduced ? 0 : Math.sin(age * 2.15 - i * .7) * .012 + Math.sin(stride - .6) * motion * .035);
      lock.rotation.x = reduced ? 0 : -headPitch * .10 + Math.sin(stride - .8) * motion * .035 + clamp(turnRate, -2, 2) * (i % 2 ? .025 : -.025);
    });
    const changed = !reduced || !lastReduced; lastReduced = reduced; return changed;
  }
  return { meshes, pose, dispose() { root.clear(); geometry.dispose(); materials.forEach(m => m.dispose()); } };
}
