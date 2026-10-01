import * as THREE from "../vendor/three.module.min.js";

// Deterministic scenery, independent of furniture picking and editable layouts.
export function createCourtyard(scene) {
  const root = new THREE.Group(); root.name = "preview-courtyard"; scene.add(root);
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshStandardMaterial({ roughness: 1 });
  const blocks = [], groundY = -.735;
  const noise = (x, z, salt = 0) => {
    const n = Math.sin(x * 127.1 + z * 311.7 + salt * 73.9) * 43758.5453;
    return n - Math.floor(n);
  };
  const box = (x, y, z, w, h, d, tint, angle = 0, snowCap = false) => blocks.push({ x, y, z, w, h, d, tint, angle, snowCap });
  const inHouse = (x, z, padding = 0) => x > -6.1 - padding && x < 6.1 + padding && z > -4.7 - padding && z < 5.9 + padding;
  const path = [[7.25, 1.25], [8.6, 1.25], [9.05, 3.5], [8.6, 6.4], [9.7, 9.1], [13, 12.5], [18, 15]];
  function pathDistance(x, z) {
    let distance = Infinity;
    for (let i = 1; i < path.length; i++) {
      const [ax, az] = path[i - 1], [bx, bz] = path[i];
      const dx = bx - ax, dz = bz - az;
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz)));
      distance = Math.min(distance, Math.hypot(x - ax - dx * t, z - az - dz * t));
    }
    return distance;
  }

  // One continuous receiving surface prevents seams and self-shadow grid lines.
  // The texture is generated locally from the same deterministic patch pattern.
  const lawnCanvas = document.createElement("canvas"); lawnCanvas.width = lawnCanvas.height = 512;
  const painter = lawnCanvas.getContext("2d");
  const grass = new THREE.Color(), darkGrass = new THREE.Color("#687e53"), lightGrass = new THREE.Color("#8fa375");
  for (let px = 0; px < 512; px += 4) for (let pz = 0; pz < 512; pz += 4) {
    const x = px / 512 * 60, z = pz / 512 * 60;
    const v = .45 + Math.sin(x * .23 + z * .17) * .19 + Math.cos(z * .28 - x * .11) * .15 + noise(x, z) * .06;
    grass.copy(darkGrass).lerp(lightGrass, v); painter.fillStyle = '#' + grass.getHexString();
    painter.fillRect(px, pz, 4, 4);
  }
  const lawnTexture = new THREE.CanvasTexture(lawnCanvas);
  lawnTexture.colorSpace = THREE.SRGBColorSpace;
  lawnTexture.wrapS = lawnTexture.wrapT = THREE.RepeatWrapping; lawnTexture.repeat.set(3, 3);
  const snowCanvas = document.createElement("canvas"); snowCanvas.width = snowCanvas.height = 256;
  const snowPainter = snowCanvas.getContext("2d"), snowColor = new THREE.Color();
  for (let x = 0; x < 256; x += 4) for (let z = 0; z < 256; z += 4) {
    snowColor.set("#d8e3e8").lerp(new THREE.Color("#f6f9f7"), .4 + noise(x, z) * .6);
    snowPainter.fillStyle = '#' + snowColor.getHexString(); snowPainter.fillRect(x, z, 4, 4);
  }
  const snowTexture = new THREE.CanvasTexture(snowCanvas);
  snowTexture.colorSpace = THREE.SRGBColorSpace;
  snowTexture.wrapS = snowTexture.wrapT = THREE.RepeatWrapping; snowTexture.repeat.set(3, 3);
  const lawnGeometry = new THREE.PlaneGeometry(180, 180);
  const lawnMaterial = new THREE.MeshStandardMaterial({ map: lawnTexture, roughness: 1 });
  const lawn = new THREE.Mesh(lawnGeometry, lawnMaterial);
  lawn.rotation.x = -Math.PI / 2; lawn.position.y = groundY; lawn.receiveShadow = true; root.add(lawn);
  // A narrow stone edge joins the existing timber foundation to the lawn.
  for (let x = -6.3; x <= 6.35; x += .5) for (const z of [-4.88, 6.06])
    box(x, groundY + .022, z, .48, .085, .43, noise(x, z) > .5 ? "#c2c1a8" : "#b4b6a0");
  for (let z = -4.4; z <= 5.8; z += .5) for (const x of [-6.32, 6.32]) {
    if (x > 0 && z > -.3 && z < 2.75) continue;
    box(x, groundY + .022, z, .43, .085, .48, "#bbbba4");
  }
  box(7.32, -.632, 1.25, .62, .19, 2.6, "#c8c8b2", 0, true);
  for (let x = 7.2; x < 19; x += .46) for (let z = -.2; z < 17; z += .46) {
    if (pathDistance(x, z) > .99 || inHouse(x, z, .1)) continue;
    const colors = ["#c7c3a9", "#d3ceb7", "#c4c2aa", "#dad3b9"];
    box(x, groundY + .023, z, .445, .068, .445, colors[Math.floor(noise(x, z, 1) * colors.length)], 0, noise(x, z) > .4);
  }
  function tuft(x, z, scale = 1, flowers = false) {
    const tint = noise(x, z) > .5 ? "#6f8c66" : "#8ca276";
    for (let i = 0; i < 3; i++) {
      const px = x + (i - 1) * .095 * scale, h = (.17 + noise(x, z, i) * .14) * scale;
      box(px, groundY + h / 2, z + (i % 2) * .08, .055 * scale, h, .05 * scale, tint, (i - 1) * .27);
      if (flowers && i !== 1)
        box(px, groundY + h, z + (i % 2) * .08, .12 * scale, .075 * scale, .12 * scale, noise(x, z, 4) > .55 ? "#ead1a0" : "#e2bcb9");
    }
  }
  for (let i = 0; i < 175; i++) {
    const x = noise(i, 1) * 34 - 17, z = noise(i, 2) * 32 - 15;
    if (inHouse(x, z, .6) || pathDistance(x, z) < 1.18) continue;
    tuft(x, z, .65 + noise(i, 3) * .7, i % 6 === 0);
  }
  function shrub(x, z, s) {
    for (let i = -2; i <= 2; i++) for (let j = -1; j <= 1; j++) {
      if (Math.abs(i) === 2 && Math.abs(j) === 1) continue;
      const h = (.27 + noise(i + x, j + z) * .22) * s;
      box(x + i * .2 * s, groundY + h / 2, z + j * .22 * s, .24 * s, h, .25 * s,
        ["#7c966d", "#90a77d", "#a5b38a"][Math.floor(noise(i, j, x) * 3)], 0, true);
    }
  }
  for (const [x, z, s] of [[-7.5, 4.1, 1.3], [-7.8, 1.5, 1.4], [2.8, 7.4, 1.1], [-3.8, 7.2, 1.15], [10.5, -.5, 1.5], [6.8, -5.8, 1.4], [-1.3, -6.7, 1.5]]) shrub(x, z, s);
  function tree(x, z, s, seed) {
    box(x, groundY + 1.38 * s, z, .24 * s, 2.76 * s, .24 * s, "#8a8168");
    box(x + .3 * s, groundY + 1.93 * s, z, .67 * s, .18 * s, .18 * s, "#8a8168", -.28);
    const colors = ["#567b53", "#6d8c59", "#7e9a69", "#4e704d", "#94a777"];
    for (let ix = -3; ix <= 3; ix++) for (let iz = -3; iz <= 3; iz++) for (let iy = 0; iy < 5; iy++) {
      if (ix * ix + iz * iz + (iy - 2) * (iy - 2) * 1.35 > 11.2 || noise(ix + seed, iz, iy) < .08) continue;
      const unit = .37 * s;
      box(x + ix * unit, groundY + (2.15 + iy * .33) * s, z + iz * unit, unit * 1.02, .35 * s, unit * 1.02,
        colors[Math.floor(noise(ix, iz + seed, iy) * colors.length)], 0, true);
    }
  }
  // Keep the open fronts clear; frame the back and outer edges instead.
  for (const [x, z, s, seed] of [[-8.8, -4.7, 1.2, 1], [-5.3, -9.2, 1.25, 2], [4.1, -9.4, 1.35, 3], [9.1, -5.4, 1.05, 4], [-13.5, 2.5, 1.15, 5], [-15, -13, 1.8, 6], [0, -18, 1.8, 7], [12.5, -15.5, 1.7, 8], [-20, -2, 1.5, 9], [21, -7, 1.8, 10]]) tree(x, z, s, seed);
  for (let i = 0; i < 12; i++) {
    const x = -10 + i * 1.48;
    box(x, groundY + .54, -7, .105, 1.08, .105, "#bcb9a0");
    if (i < 11) for (const h of [.36, .77]) box(x + .74, groundY + h, -7, 1.47, .095, .085, "#cecab1", 0, h > .5);
  }
  const mesh = new THREE.InstancedMesh(geometry, material, blocks.length);
  const matrix = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), scale = new THREE.Vector3(), tint = new THREE.Color();
  blocks.forEach((b, i) => {
    p.set(b.x, b.y, b.z); scale.set(b.w, b.h, b.d); q.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, b.angle);
    mesh.setMatrixAt(i, matrix.compose(p, q, scale)); mesh.setColorAt(i, tint.set(b.tint));
  });
  mesh.castShadow = true; mesh.receiveShadow = true; mesh.computeBoundingSphere(); root.add(mesh);

  // Snow rests on the top of vegetation, steps and fences, outside the cutaway.
  const exposed = new Map();
  blocks.filter(b => b.snowCap).forEach(b => {
    const key = `${b.x.toFixed(2)}:${b.z.toFixed(2)}`;
    if (!exposed.has(key) || exposed.get(key).y < b.y) exposed.set(key, b);
  });
  const snowMaterial = new THREE.MeshStandardMaterial({ color: "#edf4f6", roughness: .96 });
  const snowCaps = new THREE.InstancedMesh(geometry, snowMaterial, exposed.size);
  [...exposed.values()].forEach((b, i) => {
    p.set(b.x, b.y + b.h / 2 + .026, b.z); scale.set(b.w * 1.01, .064, b.d * 1.01); q.identity();
    snowCaps.setMatrixAt(i, matrix.compose(p, q, scale));
  });
  snowCaps.receiveShadow = true; snowCaps.computeBoundingSphere(); root.add(snowCaps);

  // Shallow, quiet puddles retain the weather cue when motion is reduced.
  const wetMaterial = new THREE.MeshStandardMaterial({ color: "#9fbcc3", roughness: .18, metalness: .12, transparent: true, opacity: .58 });
  const wetPlaces = [[8.7, 6.5, .8], [10.9, 10.6, 1.1], [7.7, 3.2, .7], [-8.2, 6.9, 1.2], [3.8, 8.8, .7], [-4.5, 9.8, .9], [11.8, -.7, 1.1], [-8.7, -.9, .8], [13, 7.6, .9], [5.2, -6.2, .8]];
  const puddles = new THREE.InstancedMesh(geometry, wetMaterial, wetPlaces.length * 3);
  wetPlaces.forEach(([x, z, s], i) => {
    for (let j = 0; j < 3; j++) {
      p.set(x + (j - 1) * .23 * s, groundY + (pathDistance(x, z) < 1.1 ? .061 : .013), z + (j % 2) * .17);
      scale.set((j === 1 ? 1.25 : .75) * s, .01, .42 * s); q.identity();
      puddles.setMatrixAt(i * 3 + j, matrix.compose(p, q, scale));
    }
  });
  puddles.computeBoundingSphere(); root.add(puddles);

  // The far cloud banks belong to the same 3D world as the courtyard.
  const cloudMaterial = new THREE.MeshStandardMaterial({ color: "#edf3ef", roughness: 1, transparent: true, opacity: .66, depthWrite: false });
  const cloudBanks = new THREE.InstancedMesh(geometry, cloudMaterial, 15);
  [[-19, 8, -27], [-3, 11, -32], [19, 10, -25]].forEach(([x, y, z], i) => {
    for (let j = 0; j < 5; j++) {
      p.set(x + (j - 2) * 1.6, y + (j % 2) * .5, z + (j % 3) * .35);
      scale.set(2.8, .55 + noise(i, j) * .55, 1.5); q.identity();
      cloudBanks.setMatrixAt(i * 5 + j, matrix.compose(p, q, scale));
    }
  });
  cloudBanks.computeBoundingSphere(); root.add(cloudBanks);

  const particleMaterial = new THREE.MeshBasicMaterial({ color: "#d6e7f1", transparent: true, opacity: .6, depthWrite: false });
  const particles = new THREE.InstancedMesh(geometry, particleMaterial, 640);
  particles.instanceMatrix.setUsage(THREE.DynamicDrawUsage); particles.frustumCulled = false; root.add(particles);
  const rainAxis = new THREE.Vector3(0, 0, 1);
  const seeds = Array.from({ length: 640 }, (_, i) => {
    let x, z, attempt = 0;
    do { x = noise(i, 11, attempt) * 40 - 19; z = noise(i, 12, attempt++) * 40 - 17; } while (inHouse(x, z, .8));
    return { x, z, phase: noise(i, 13), size: .72 + noise(i, 14) * .55 };
  });
  let condition = "clear", light = "day", elapsed = 0, particleCount = 0;
  function poseParticles(time) {
    const snowing = condition === "snow", speed = snowing ? .072 : condition === "storm" ? .94 : .66;
    for (let i = 0; i < particleCount; i++) {
      const seed = seeds[i], fall = (seed.phase + time * speed) % 1;
      p.set(seed.x + (snowing ? Math.sin(time * .8 + i) * .18 : 0), groundY + .06 + (1 - fall) * 10.5, seed.z);
      if (snowing) { scale.setScalar(.066 * seed.size); q.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, time * .22 + i); }
      else { scale.set(.017, (condition === "storm" ? .52 : .35) * seed.size, .017); q.setFromAxisAngle(rainAxis, -.12); }
      particles.setMatrixAt(i, matrix.compose(p, q, scale));
    }
    particles.instanceMatrix.needsUpdate = true;
  }
  function setWeather(nextCondition, nextLight) {
    condition = nextCondition; light = nextLight;
    const snowing = condition === "snow", wet = ["rain", "storm"].includes(condition), night = light === "night";
    const cloudy = ["cloudy", "rain", "storm", "snow", "mist"].includes(condition);
    lawnMaterial.map = snowing ? snowTexture : lawnTexture; lawnMaterial.needsUpdate = true;
    lawnMaterial.color.set(wet ? "#a2b9bc" : condition === "mist" ? "#d7e2db" : "#ffffff");
    lawnMaterial.roughness = wet ? .66 : 1;
    material.color.set(wet ? "#b5c5ca" : "#ffffff"); material.roughness = wet ? .73 : 1;
    puddles.visible = wet; snowCaps.visible = snowing; cloudBanks.visible = cloudy;
    cloudMaterial.color.set(night ? "#748799" : condition === "storm" ? "#8c9da7" : condition === "rain" ? "#becdd2" : "#e5eded");
    cloudMaterial.opacity = condition === "mist" ? .33 : .66;
    particleCount = snowing ? 230 : condition === "storm" ? 640 : wet ? 430 : 0;
    particles.visible = particleCount > 0; particles.count = particleCount;
    particleMaterial.color.set(snowing ? "#ffffff" : night ? "#b1c5df" : "#d6e7f1");
    particleMaterial.opacity = snowing ? .9 : condition === "storm" ? .63 : .5;
    poseParticles(elapsed);
  }
  setWeather("clear", "day");
  return {
    setWeather,
    tick(time) { if (!particleCount) return false; elapsed = time; poseParticles(time); return true; },
    getState() { return { condition, light, particles: particleCount, elapsed, snowCover: snowCaps.visible, wetGround: puddles.visible, clouds: cloudBanks.visible }; },
    dispose() {
      root.removeFromParent();
      [mesh, snowCaps, puddles, cloudBanks, particles].forEach(item => item.dispose());
      [geometry, material, lawnTexture, snowTexture, lawnGeometry, lawnMaterial, snowMaterial, wetMaterial, cloudMaterial, particleMaterial].forEach(item => item.dispose());
    }
  };
}
