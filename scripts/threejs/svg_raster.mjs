#!/usr/bin/env node
/**
 * svg_raster.mjs — headless Chromium SVG 2.0 RGBA rasterizer for surgical-media.
 *
 * Uses native Node >= 22 WebSocket + fetch over Chrome DevTools Protocol
 * (zero npm dependencies). Renders full SVG 2.0 — gradients, filters, masks,
 * clipPaths, <style> classes, <use>, fill-rule="evenodd" — at exact pixel size
 * with true alpha transparency (`omitBackground: true`).
 *
 * Usage:
 *   node scripts/threejs/svg_raster.mjs \
 *     --input in.svg --output out.png --width 640 --height 360 --browser /snap/bin/chromium
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

function parseArgs(argv) {
  const args = { input: null, output: null, width: 512, height: 512, browser: null };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const next = argv[i + 1];
    if (flag === "--input") {
      args.input = next;
      i++;
    } else if (flag === "--output") {
      args.output = next;
      i++;
    } else if (flag === "--width") {
      args.width = Number.parseInt(next, 10);
      i++;
    } else if (flag === "--height") {
      args.height = Number.parseInt(next, 10);
      i++;
    } else if (flag === "--browser") {
      args.browser = next;
      i++;
    }
  }
  if (!args.input || !args.output || !args.browser) {
    throw new Error("--input, --output, and --browser are required");
  }
  return args;
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

  send(method, params = {}, timeoutMs = 15000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP command ${method} timed out after ${timeoutMs}ms`));
        }
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (val) => {
          clearTimeout(timer);
          resolve(val);
        },
        reject: (err) => {
          clearTimeout(timer);
          reject(err);
        },
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    if (this.ws && this.ws.readyState <= 1) {
      this.ws.close();
    }
  }
}

function startSvgServer(svgText, width, height) {
  // Strip any <script> tags defensively; CSP blocks all external network loads.
  const safeSvg = svgText.replace(/<script[\s\S]*?<\/script>/gi, "");
  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:;" />
<style>
  html, body {
    margin: 0; padding: 0; width: ${width}px; height: ${height}px;
    overflow: hidden; background: transparent;
    display: flex; align-items: center; justify-content: center;
  }
  svg {
    width: 100%; height: 100%; display: block;
  }
</style>
</head>
<body>${safeSvg}</body>
</html>`;

  const server = http.createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(html);
  });

  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, port: server.address().port });
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
      "--disable-dev-shm-usage",
      "--remote-debugging-port=0",
      `--user-data-dir=${userDataDir}`,
      `--window-size=${width},${height}`,
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );

  const ready = new Promise((resolve, reject) => {
    let stderrBuf = "";
    const timer = setTimeout(() => {
      reject(new Error(`Chromium startup timed out. stderr:\n${stderrBuf}`));
    }, 15000);
    proc.stderr.on("data", (chunk) => {
      stderrBuf += chunk.toString("utf8");
      const m = stderrBuf.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:(\d+)\/[^\s]+)/);
      if (m) {
        clearTimeout(timer);
        resolve({ debugPort: Number(m[2]) });
      }
    });
    proc.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    proc.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Chromium exited prematurely (${code}). stderr:\n${stderrBuf}`));
    });
  });

  return { proc, ready };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const svgText = fs.readFileSync(args.input, "utf8");
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "sm-svg-chrome-"));
  const { server, port } = await startSvgServer(svgText, args.width, args.height);

  let chromeProc = null;
  let cdp = null;

  try {
    const launched = launchChromium(args.browser, userDataDir, args.width, args.height);
    chromeProc = launched.proc;
    const { debugPort } = await launched.ready;

    let pageWsUrl = null;
    for (let i = 0; i < 20; i++) {
      const res = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) {
        pageWsUrl = page.webSocketDebuggerUrl;
        break;
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    if (!pageWsUrl) throw new Error("No Chromium page target found");

    cdp = new CDPClient(pageWsUrl);
    await cdp.connect();
    await cdp.send("Page.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: args.width,
      height: args.height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp.send("Emulation.setDefaultBackgroundColorOverride", {
      color: { r: 0, g: 0, b: 0, a: 0 },
    });
    await cdp.send("Page.navigate", { url: `http://127.0.0.1:${port}/` });

    // Wait for DOM ready
    for (let i = 0; i < 50; i++) {
      const st = await cdp.send("Runtime.evaluate", {
        expression: "document.readyState",
        returnByValue: true,
      });
      if (st?.result?.value === "complete") break;
      await new Promise((r) => setTimeout(r, 50));
    }

    const shot = await cdp.send("Page.captureScreenshot", {
      format: "png",
      omitBackground: true,
      clip: { x: 0, y: 0, width: args.width, height: args.height, scale: 1 },
    });
    fs.writeFileSync(args.output, Buffer.from(shot.data, "base64"));
  } finally {
    if (cdp) {
      try {
        cdp.close();
      } catch {
        // ignore
      }
    }
    if (chromeProc && !chromeProc.killed) {
      chromeProc.kill("SIGKILL");
    }
    server.close();
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
