#!/usr/bin/env node
/**
 * runner.mjs — headless Three.js WebGL frame + anchor-track baker for surgical-media.
 *
 * Drives a local Chromium/Chrome binary over native Chrome DevTools Protocol
 * (Node >= 22 built-in WebSocket + fetch; zero browser-automation npm deps).
 * Serves stage.html, scenes.mjs, the full local `three` package (including
 * `examples/jsm/` for RoomEnvironment, EffectComposer, UnrealBloomPass,
 * GLTFLoader, SVGLoader), plus optional per-project custom scene scripts and
 * local `.glb`/`.gltf` assets on 127.0.0.1:0 — 100% offline and deterministic.
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".bin": "application/octet-stream",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
};

function parseArgs(argv) {
  const args = {
    spec: null,
    outDir: null,
    width: 1280,
    height: 720,
    fps: 30,
    frames: 30,
    browser: null,
    threeModule: null,
    baseDir: null,
  };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const next = argv[i + 1];
    if (flag === "--spec") {
      args.spec = next;
      i++;
    } else if (flag === "--out-dir") {
      args.outDir = next;
      i++;
    } else if (flag === "--width") {
      args.width = Number.parseInt(next, 10);
      i++;
    } else if (flag === "--height") {
      args.height = Number.parseInt(next, 10);
      i++;
    } else if (flag === "--fps") {
      args.fps = Number.parseInt(next, 10);
      i++;
    } else if (flag === "--frames") {
      args.frames = Number.parseInt(next, 10);
      i++;
    } else if (flag === "--browser") {
      args.browser = next;
      i++;
    } else if (flag === "--three-module") {
      args.threeModule = next;
      i++;
    } else if (flag === "--base-dir") {
      args.baseDir = next;
      i++;
    }
  }
  if (!args.spec || !args.outDir || !args.browser || !args.threeModule) {
    throw new Error(
      "Missing required args: --spec, --out-dir, --browser, and --three-module are required",
    );
  }
  return args;
}

function safeResolveUnder(rootDir, relPath) {
  const root = path.resolve(rootDir);
  const candidate = path.resolve(root, relPath);
  if (candidate !== root && !candidate.startsWith(root + path.sep)) {
    return null;
  }
  return candidate;
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = (ev) => {
        cleanup();
        reject(new Error(`CDP WebSocket error: ${ev.message || "connection failed"}`));
      };
      const cleanup = () => {
        this.ws.removeEventListener("open", onOpen);
        this.ws.removeEventListener("error", onError);
      };
      this.ws.addEventListener("open", onOpen);
      this.ws.addEventListener("error", onError);
    });

    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(typeof ev.data === "string" ? ev.data : ev.data.toString());
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) {
          reject(new Error(`CDP error (${msg.error.code}): ${msg.error.message}`));
        } else {
          resolve(msg.result);
        }
      }
    });

    this.ws.addEventListener("close", () => {
      for (const { reject } of this.pending.values()) {
        reject(new Error("CDP WebSocket closed unexpectedly"));
      }
      this.pending.clear();
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    if (this.ws && this.ws.readyState <= 1) {
      this.ws.close();
    }
  }
}

function startStaticServer({ spec, width, height, threeModule, baseDir }) {
  const stageHtml = fs.readFileSync(path.join(__dirname, "stage.html"), "utf8");
  const scenesJs = fs.readFileSync(path.join(__dirname, "scenes.mjs"), "utf8");
  const threeBuildDir = path.dirname(path.resolve(threeModule));
  const threePkgRoot = path.resolve(threeBuildDir, "..");

  // Optional custom scene script & external 3D asset (resolved against baseDir)
  const params = spec && typeof spec.params === "object" && spec.params ? spec.params : {};
  const resolveLocal = (rawPath) => {
    if (!rawPath || typeof rawPath !== "string") return null;
    if (path.isAbsolute(rawPath)) {
      return fs.existsSync(rawPath) && fs.statSync(rawPath).isFile() ? rawPath : null;
    }
    const anchorDir = baseDir ? path.resolve(baseDir) : process.cwd();
    const resolved = path.resolve(anchorDir, rawPath);
    return fs.existsSync(resolved) && fs.statSync(resolved).isFile() ? resolved : null;
  };

  const customScriptPath = resolveLocal(params.threejs_script);
  const externalAssetPath = resolveLocal(params.asset_path);

  const clientSpec = {
    ...spec,
    _runtime: {
      hasCustomScript: Boolean(customScriptPath),
      assetUrl: externalAssetPath
        ? `/asset${path.extname(externalAssetPath).toLowerCase()}`
        : null,
    },
  };
  const configJson = JSON.stringify({ spec: clientSpec, width, height });

  const serveFile = (res, filePath) => {
    const ext = path.extname(filePath).toLowerCase();
    const mime = MIME_TYPES[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": mime });
    res.end(fs.readFileSync(filePath));
  };

  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
    if (urlPath === "/" || urlPath === "/index.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(stageHtml);
    } else if (urlPath === "/scenes.mjs") {
      res.writeHead(200, { "Content-Type": "application/javascript; charset=utf-8" });
      res.end(scenesJs);
    } else if (urlPath === "/config.json") {
      res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      res.end(configJson);
    } else if (urlPath === "/custom_scene.mjs" && customScriptPath) {
      serveFile(res, customScriptPath);
    } else if (
      externalAssetPath &&
      urlPath === `/asset${path.extname(externalAssetPath).toLowerCase()}`
    ) {
      serveFile(res, externalAssetPath);
    } else if (urlPath.startsWith("/three/")) {
      const rel = urlPath.slice("/three/".length);
      const target = safeResolveUnder(threePkgRoot, rel);
      if (target && fs.existsSync(target) && fs.statSync(target).isFile()) {
        serveFile(res, target);
      } else {
        res.writeHead(404);
        res.end("Not found");
      }
    } else {
      res.writeHead(404);
      res.end("Not found");
    }
  });

  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      resolve({ server, port: addr.port });
    });
  });
}

function launchChromium(browserBinary, userDataDir, width, height) {
  const proc = spawn(
    browserBinary,
    [
      "--headless",
      "--no-sandbox",
      "--disable-gpu-sandbox",
      "--enable-unsafe-swiftshader",
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--disable-dev-shm-usage",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--remote-debugging-port=0",
      `--user-data-dir=${userDataDir}`,
      `--window-size=${width},${height}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );

  const ready = new Promise((resolve, reject) => {
    let stderrBuf = "";
    const timer = setTimeout(() => {
      reject(new Error(`Chromium DevTools startup timed out. stderr:\n${stderrBuf}`));
    }, 20000);

    proc.stderr.on("data", (chunk) => {
      stderrBuf += chunk.toString("utf8");
      const m = stderrBuf.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:(\d+)\/[^\s]+)/);
      if (m) {
        clearTimeout(timer);
        resolve({ browserWsUrl: m[1], debugPort: Number(m[2]) });
      }
    });

    proc.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });

    proc.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Chromium exited prematurely with code ${code}. stderr:\n${stderrBuf}`));
    });
  });

  return { proc, ready };
}

async function getPageWsUrl(debugPort) {
  for (let attempt = 0; attempt < 20; attempt++) {
    const res = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
    const targets = await res.json();
    const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
    if (page) return page.webSocketDebuggerUrl;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("Could not find Chromium page target on DevTools endpoint");
}

async function waitForThreeReady(cdp) {
  for (let attempt = 0; attempt < 200; attempt++) {
    const res = await cdp.send("Runtime.evaluate", {
      expression: "({ ready: Boolean(window.__THREE_READY__), error: window.__THREE_ERROR__ || null })",
      returnByValue: true,
    });
    const val = res?.result?.value;
    if (val?.error) {
      throw new Error(`Three.js stage error: ${val.error}`);
    }
    if (val?.ready) {
      return;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("Timed out waiting for Three.js stage to initialize");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const spec = JSON.parse(fs.readFileSync(args.spec, "utf8"));
  fs.mkdirSync(args.outDir, { recursive: true });

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "sm-threejs-chrome-"));
  const { server, port } = await startStaticServer({
    spec,
    width: args.width,
    height: args.height,
    threeModule: args.threeModule,
    baseDir: args.baseDir,
  });

  let chromeProc = null;
  let cdp = null;

  try {
    const launched = launchChromium(args.browser, userDataDir, args.width, args.height);
    chromeProc = launched.proc;
    const { debugPort } = await launched.ready;

    const pageWsUrl = await getPageWsUrl(debugPort);
    cdp = new CDPClient(pageWsUrl);
    await cdp.connect();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Page.navigate", { url: `http://127.0.0.1:${port}/` });

    await waitForThreeReady(cdp);

    const totalFrames = Math.max(1, args.frames);
    const framesOut = [];

    for (let idx = 0; idx < totalFrames; idx++) {
      const evalRes = await cdp.send("Runtime.evaluate", {
        expression: `window.__renderFrame(${idx}, ${totalFrames})`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (evalRes.exceptionDetails) {
        throw new Error(
          `Frame ${idx + 1} render exception: ${evalRes.exceptionDetails.text || JSON.stringify(evalRes.exceptionDetails)}`,
        );
      }
      const { pngBase64, anchors } = evalRes.result.value;
      const framePath = path.join(
        args.outDir,
        `frame_${String(idx + 1).padStart(4, "0")}.png`,
      );
      fs.writeFileSync(framePath, Buffer.from(pngBase64, "base64"));
      framesOut.push({ frame: idx + 1, anchors });
    }

    const tracksPayload = {
      total_frames: totalFrames,
      frames: framesOut,
    };
    fs.writeFileSync(
      path.join(args.outDir, "anchor_tracks.json"),
      JSON.stringify(tracksPayload, null, 2),
      "utf8",
    );
  } finally {
    if (cdp) {
      try {
        cdp.close();
      } catch {
        // ignore close errors
      }
    }
    if (chromeProc && !chromeProc.killed) {
      chromeProc.kill("SIGKILL");
    }
    server.close();
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup errors
    }
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
