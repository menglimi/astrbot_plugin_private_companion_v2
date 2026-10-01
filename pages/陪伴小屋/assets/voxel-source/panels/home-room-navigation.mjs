// Local floor navigation only; it never decides or advances a life activity.
export function isRoomPointFree(point, world, radius = .25, ignore = []) {
  const { minX, maxX, minZ, maxZ } = world.bounds;
  if (point.x - radius < minX || point.x + radius > maxX || point.z - radius < minZ || point.z + radius > maxZ) return false;
  return !world.obstacles.some(box => {
    if (ignore.includes(box.id)) return false;
    const dx = point.x - box.x, dz = point.z - box.z;
    const x = Math.cos(box.angle) * dx - Math.sin(box.angle) * dz;
    const z = Math.sin(box.angle) * dx + Math.cos(box.angle) * dz;
    const qx = Math.max(0, Math.abs(x) - box.halfX), qz = Math.max(0, Math.abs(z) - box.halfZ);
    return qx * qx + qz * qz <= radius * radius;
  });
}

export function roomSegmentFree(a, b, world, radius = .25, ignore = []) {
  const steps = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.z - a.z) / .08));
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    if (!isRoomPointFree({ x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t }, world, radius, ignore)) return false;
  }
  return true;
}

export function nearestRoomPoint(point, world, radius = .25) {
  let best = null, distance = Infinity;
  for (let x = world.bounds.minX + radius; x <= world.bounds.maxX - radius; x += .28) {
    for (let z = world.bounds.minZ + radius; z <= world.bounds.maxZ - radius; z += .28) {
      const next = (x - point.x) ** 2 + (z - point.z) ** 2;
      if (next < distance && isRoomPointFree({ x, z }, world, radius)) { best = { x, z }; distance = next; }
    }
  }
  return best;
}

export function roomRoute(start, target, world, radius = .25) {
  if (!isRoomPointFree(start, world, radius) || !isRoomPointFree(target, world, radius)) return [];
  if (roomSegmentFree(start, target, world, radius)) return [{ ...target }];
  const step = .28, x0 = world.bounds.minX + radius, z0 = world.bounds.minZ + radius;
  const width = Math.floor((world.bounds.maxX - radius - x0) / step) + 1;
  const height = Math.floor((world.bounds.maxZ - radius - z0) / step) + 1;
  const point = key => ({ x: x0 + key % width * step, z: z0 + Math.floor(key / width) * step });
  const free = Array.from({ length: width * height }, (_, key) => isRoomPointFree(point(key), world, radius));
  function endpoint(value) {
    const sorted = free.map((ok, key) => ({ ok, key, distance: Math.hypot(point(key).x - value.x, point(key).z - value.z) }))
      .filter(item => item.ok).sort((a, b) => a.distance - b.distance);
    return sorted.find(item => roomSegmentFree(value, point(item.key), world, radius))?.key;
  }
  const from = endpoint(start), to = endpoint(target);
  if (from === undefined || to === undefined) return [];
  const queue = [from], previous = new Map([[from, null]]);
  for (let cursor = 0; cursor < queue.length && !previous.has(to); cursor++) {
    const key = queue[cursor], col = key % width, row = Math.floor(key / width);
    const neighbors = [col > 0 ? key - 1 : -1, col + 1 < width ? key + 1 : -1, row > 0 ? key - width : -1, row + 1 < height ? key + width : -1];
    for (const next of neighbors) if (next >= 0 && free[next] && !previous.has(next) && roomSegmentFree(point(key), point(next), world, radius)) {
      previous.set(next, key); queue.push(next);
    }
  }
  if (!previous.has(to)) return [];
  const path = [target];
  for (let key = to; key !== null; key = previous.get(key)) path.unshift(point(key));
  const result = []; let origin = start;
  for (let i = 0; i < path.length;) {
    let end = i;
    while (end + 1 < path.length && roomSegmentFree(origin, path[end + 1], world, radius)) end++;
    result.push(path[end]); origin = path[end]; i = end + 1;
  }
  return result;
}
