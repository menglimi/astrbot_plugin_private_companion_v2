import * as THREE from "../vendor/three.module.min.js";

// A front-facing paper resident in the same world/depth space as furniture.
// This is deliberately not a Spine loader or a fabricated rear view.
export function createPaperRig(parent, module) {
  const group = new THREE.Group(); parent.add(group);
  const geometry = new THREE.PlaneGeometry(2.4, 2.4);
  const material = new THREE.MeshBasicMaterial({ transparent: true, alphaTest: .12, depthWrite: true, side: THREE.DoubleSide, toneMapped: false });
  const mesh = new THREE.Mesh(geometry, material); group.add(mesh);
  mesh.position.y = (module.foot_y - 128) * 2.4 / 256;
  mesh.userData.station = "resident";
  let disposed = false, ready = false, failed = false, pixels = null, time = 0, action = "idle", frame = -1, mirror = 1;
  let texture = new THREE.TextureLoader().load(module.atlas, loaded => {
    if (disposed) { loaded.dispose(); return; }
    const canvas = document.createElement("canvas"); canvas.width = loaded.image.width; canvas.height = loaded.image.height;
    const context = canvas.getContext("2d", { willReadFrequently: true }); context.drawImage(loaded.image, 0, 0);
    pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    ready = true; material.map = loaded; material.needsUpdate = true; frame = -1;
  }, undefined, () => { failed = true; });
  texture.colorSpace = THREE.SRGBColorSpace; texture.generateMipmaps = false;
  texture.minFilter = texture.magFilter = THREE.LinearFilter;
  texture.repeat.set(1 / module.columns, 1 / module.rows);
  mesh.visible = false;
  const raycast = mesh.raycast.bind(mesh);
  mesh.raycast = (ray, hits) => {
    if (!ready || frame < 0) return;
    const candidates = []; raycast(ray, candidates);
    for (const hit of candidates) {
      const x = frame * 256 + Math.min(255, Math.floor(hit.uv.x * 256));
      const y = module.actions[action].row * 256 + Math.min(255, Math.floor((1 - hit.uv.y) * 256));
      if (pixels.data[(y * pixels.width + x) * 4 + 3] > 32) hits.push(hit);
    }
  };
  return {
    meshes: [mesh],
    get ready() { return ready; }, get failed() { return failed; },
    pose(dt, intent) {
      const next = intent.sitting > .5 ? (intent.attention > .4 ? "wave_seated" : intent.reading ? "read" : "sit") : intent.attention > .4 ? "wave" : intent.speed > .04 ? "walk" : "idle";
      if (next !== action) { action = next; time = 0; }
      if (!intent.reduced) time += dt;
      const clip = module.actions[action], nextFrame = intent.reduced ? 0 : Math.floor(time * clip.fps) % clip.frames;
      const previousYaw = group.rotation.y, previousMirror = mirror;
      group.rotation.y = intent.gazeYaw || 0;
      if (action === "walk" && Math.abs(Math.sin(group.rotation.y)) > .3) mirror = Math.sin(group.rotation.y) > 0 ? -1 : 1;
      if (action !== "walk") mirror = 1;
      mesh.scale.x = mirror;
      const changed = ready && (frame !== nextFrame || texture.offset.y !== 1 - (clip.row + 1) / module.rows);
      if (changed) {
        frame = nextFrame; texture.offset.set(frame / module.columns, 1 - (clip.row + 1) / module.rows);
        mesh.visible = true;
      }
      return changed || previousYaw !== group.rotation.y || previousMirror !== mirror;
    },
    dispose() { disposed = true; group.removeFromParent(); geometry.dispose(); material.dispose(); texture.dispose(); pixels = null; },
  };
}
