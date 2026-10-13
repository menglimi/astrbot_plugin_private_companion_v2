// JSONL bridge for the emotion engine bundled in Companion V2.
import readline from "node:readline";
import {
  SoullinkRuntime,
  facsKeys,
  getVADPreset,
  motionStylePresets,
} from "./vendor/soullink_emotion_engine/index.mjs";

const DIRECTIONAL_CHANNELS = new Set([
  "gazeX", "gazeY", "headX", "headY", "headZ", "bodyX", "bodyY", "bodyZ",
]);

const EMOTION_ALIASES = new Map(Object.entries({
  中性: "neutral",
  默认: "neutral",
  普通: "neutral",
  无情绪: "neutral",
  平静: "calm",
  开心: "happy",
  快乐: "happy",
  高兴: "happy",
  兴奋: "excited",
  激动: "excited",
  高能: "excited",
  惊喜: "excited",
  惊讶: "excited",
  害羞: "shy",
  羞涩: "shy",
  脸红: "shy",
  好奇: "curious",
  疑问: "curious",
  疑惑: "confused",
  困惑: "confused",
  担心: "concerned",
  关切: "concerned",
  焦虑: "concerned",
  紧张: "concerned",
  难过: "sad",
  伤心: "sad",
  悲伤: "sad",
  生气: "anger",
  愤怒: "anger",
  恼火: "anger",
  喜欢: "affectionate",
  喜爱: "affectionate",
  爱心: "affectionate",
  贴贴: "affectionate",
  疲惫: "tired",
  疲劳: "tired",
  累: "tired",
  困: "tired",
  任意: "any",
  全部: "any",
  angry: "anger",
  mad: "anger",
  furious: "anger",
  anxious: "concerned",
  anxiety: "concerned",
  joy: "happy",
  joyful: "happy",
  happiness: "happy",
  love: "affectionate",
  loving: "affectionate",
  surprised: "excited",
  surprise: "excited",
  confusion: "confused",
  puzzled: "confused",
  curiosity: "curious",
  concern: "concerned",
  worried: "concerned",
  worry: "concerned",
  shyness: "shy",
  all: "any",
}));

function normalizeEmotion(value) {
  const name = String(value || "").trim().toLowerCase().replace(/\s+/gu, "_");
  return EMOTION_ALIASES.get(name) || name;
}

const PARAMETER_MAP = Object.fromEntries(facsKeys.map((key) => [
  key,
  {
    target: key,
    min: DIRECTIONAL_CHANNELS.has(key) ? -1 : 0,
    max: key === "eyeOpen" ? 1.25 : 1,
  },
]));

const PARAMETER_SMOOTHING = Object.fromEntries(facsKeys.map((key) => {
  let speed = 2.4;
  if (key === "eyeBlinkL" || key === "eyeBlinkR") speed = 28;
  else if (key === "eyeOpen") speed = 12;
  else if (key.startsWith("gaze")) speed = 3.2;
  else if (key.startsWith("head")) speed = 1.4;
  else if (key.startsWith("body")) speed = 1.2;
  else if (key === "breath") speed = 3.5;
  return [key, speed];
}));

const MOTION_STYLE_TUNING = {
  natural: {
    spontaneity: 1.38,
    gazeStability: 0.64,
    microMotionGain: 1.42,
    idleActionGain: 1.32,
  },
  lively: {
    spontaneity: 2,
    gestureFrequency: 1.95,
    gazeStability: 0.38,
    blinkRate: 1.32,
    breathRate: 1.14,
    breathVariance: 0.74,
    microMotionGain: 2,
    idleActionGain: 1.92,
    avoidRepeatWindow: 2,
    speechAccentGain: 1.58,
  },
  calm: {
    spontaneity: 0.82,
    microMotionGain: 0.9,
    idleActionGain: 0.9,
  },
  shy: {
    spontaneity: 1.08,
    microMotionGain: 1.08,
    idleActionGain: 1.02,
  },
};

const BASE_EMOTION_PERSONALITY = {
  baseline: { valence: 0.006, arousal: 0, dominance: 0.003 },
  ambientDriftStrength: 0.004,
  emotionHoldSeconds: 8,
  targetApproachRate: 1.2,
};

const EMOTION_PERSONALITY_TUNING = {
  lively: {
    baseline: { valence: 0.03, arousal: 0.045, dominance: 0.012 },
    ambientDriftStrength: 0.018,
    emotionHoldSeconds: 12,
    targetApproachRate: 1.68,
    reactivity: 1.28,
    emotionBias: {
      happy: 1.14,
      excited: 1.24,
      curious: 1.12,
      surprised: 1.18,
    },
  },
};

const PROFILE = {
  modelId: "private-companion-v2-vts",
  displayName: "Companion V2 VTube Studio",
  version: "1",
  modelPath: "vts://current-model",
  schemaVersion: 2,
  parameterMap: PARAMETER_MAP,
  parameterSmoothing: PARAMETER_SMOOTHING,
  neutralParams: {
    eyeOpen: 1,
    mouthSmile: 0.04,
    breath: 0.5,
  },
  capabilities: {
    headControl: true,
    bodyControl: true,
    eyeBlink: true,
    eyeSmile: true,
    gazeControl: true,
    mouthOpen: true,
    mouthSmile: true,
    browControl: true,
    blush: true,
    tear: false,
    sweat: false,
    breath: true,
  },
  idleConfig: {
    gazeX: [-0.18, 0.18],
    gazeY: [-0.1, 0.12],
    bodyX: [-0.075, 0.075],
    bodyY: [-0.032, 0.038],
    bodyZ: [-0.085, 0.085],
    headX: [-0.11, 0.11],
    headY: [-0.085, 0.095],
    headZ: [-0.09, 0.09],
  },
};

let runtime;
let fps = 20;
let timer = null;
let startedAt = performance.now() / 1000;
let previousTime = startedAt;
let styleName = "natural";

function write(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function clamp(value, min, max, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback;
}

function nowSeconds() {
  return performance.now() / 1000 - startedAt;
}

function createRuntime(options = {}) {
  styleName = Object.hasOwn(motionStylePresets, options.style) ? options.style : styleName;
  runtime = new SoullinkRuntime({
    profile: PROFILE,
    motionStyle: {
      ...motionStylePresets[styleName],
      ...MOTION_STYLE_TUNING[styleName],
      ...(options.motionStyle || {}),
    },
    emotionPersonality: {
      ...BASE_EMOTION_PERSONALITY,
      ...(EMOTION_PERSONALITY_TUNING[styleName] || {}),
    },
  });
  runtime.setParameterGain(clamp(options.parameterGain, 0.4, 5, 1.7));
  runtime.setBodyMotionGain(clamp(options.bodyMotionGain, 0, 4, 1.6));
  runtime.setVADDecayRate(clamp(options.vadDecayRate, 0, 1, 0.075));
}

function restartTimer(nextFps = fps) {
  fps = Math.round(clamp(nextFps, 5, 30, 20));
  if (timer) clearInterval(timer);
  previousTime = performance.now() / 1000;
  timer = setInterval(tick, Math.round(1000 / fps));
  timer.unref?.();
}

function tick() {
  const absolute = performance.now() / 1000;
  const delta = Math.min(0.1, Math.max(0.001, absolute - previousTime));
  previousTime = absolute;
  try {
    emitSnapshot(runtime.update(absolute - startedAt, delta));
  } catch (error) {
    write({ type: "error", error: String(error?.message || error) });
  }
}

function emitSnapshot(snapshot = runtime.getSnapshot()) {
  write({
    type: "frame",
    state: snapshot.state,
    intent: snapshot.emotionIntent,
    vad: snapshot.vad,
    facs: snapshot.facs,
    live2dParams: snapshot.live2dParams,
    actionUnits: snapshot.actionUnits,
    motionStyle: snapshot.motionStyle,
    parameterGain: snapshot.parameterGain,
    bodyMotionGain: snapshot.bodyMotionGain,
    time: nowSeconds(),
  });
}

function normalizeVAD(value, fallback) {
  const source = value && typeof value === "object" ? value : {};
  return {
    valence: clamp(source.valence, -1, 1, fallback.valence),
    arousal: clamp(source.arousal, -1, 1, fallback.arousal),
    dominance: clamp(source.dominance, -1, 1, fallback.dominance),
  };
}

function triggerIntent(payload = {}) {
  const emotion = normalizeEmotion(payload.emotion || "neutral") || "neutral";
  const variant = String(payload.variant || "").trim() || undefined;
  const preset = getVADPreset(emotion, variant);
  const vadTarget = normalizeVAD(payload.vad || payload.vadTarget, preset);
  const naturalEmotion = normalizeEmotion(payload.naturalEmotion || emotion) || emotion;
  const intent = {
    emotion,
    variant,
    naturalEmotion,
    naturalVariant: String(payload.naturalVariant || variant || "") || undefined,
    naturalVAD: vadTarget,
    intensity: clamp(payload.intensity, 0, 1, 0.7),
    contextTags: Array.isArray(payload.contextTags)
      ? payload.contextTags.map(String).slice(0, 12)
      : ["astrbot"],
    sourceMessage: String(payload.sourceMessage || "").slice(0, 1000),
  };
  runtime.triggerIntent(intent, nowSeconds(), { vadTarget });
  emitSnapshot();
}

function configure(payload = {}) {
  const nextStyle = Object.hasOwn(motionStylePresets, payload.style) ? payload.style : styleName;
  const oldSnapshot = runtime?.getSnapshot?.();
  const options = {
    style: nextStyle,
    motionStyle: payload.motionStyle,
    parameterGain: payload.parameterGain ?? oldSnapshot?.parameterGain,
    bodyMotionGain: payload.bodyMotionGain ?? oldSnapshot?.bodyMotionGain,
    vadDecayRate: payload.vadDecayRate ?? oldSnapshot?.vad?.decayRate,
  };
  createRuntime(options);
  restartTimer(payload.fps ?? fps);
  write({ type: "configured", fps, style: styleName });
}

function handle(command) {
  const op = String(command?.op || "");
  if (op === "trigger") {
    triggerIntent(command.intent || command);
  } else if (op === "message") {
    runtime.sendMessage(String(command.text || ""), nowSeconds());
    emitSnapshot();
  } else if (op === "configure") {
    configure(command);
  } else if (op === "reset") {
    runtime.reset(nowSeconds());
    emitSnapshot();
  } else if (op === "snapshot") {
    emitSnapshot();
  } else if (op === "shutdown") {
    if (timer) clearInterval(timer);
    write({ type: "stopped" });
    process.exit(0);
  } else {
    write({ type: "error", error: `Unknown operation: ${op}` });
  }
}

createRuntime();
restartTimer(Number(process.argv[2]) || 20);

const input = readline.createInterface({ input: process.stdin, terminal: false });
input.on("line", (line) => {
  try {
    handle(JSON.parse(line));
  } catch (error) {
    write({ type: "error", error: String(error?.message || error) });
  }
});
input.on("close", () => {
  if (timer) clearInterval(timer);
});

write({
  type: "ready",
  engine: "@soullink-emotion/engine",
  version: "0.1.0-beta.1",
  fps,
  styles: Object.keys(motionStylePresets),
});
