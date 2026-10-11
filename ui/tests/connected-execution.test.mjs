import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { access, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { promisify } from "node:util";
import { createServer } from "vite";

const browser = process.env.LABFORGE_TEST_BROWSER ?? "/usr/bin/google-chrome";
const installed = await access(browser).then(() => true, () => false);
let server;
let base;
let cache;
before(async () => {
  if (!installed) return;
  cache = await mkdtemp(join(tmpdir(), "labforge-vite-test-"));
  server = await createServer({
    cacheDir: cache,
    plugins: [{ name: "block-test-backend-requests", configureServer(vite) {
      vite.middlewares.use("/api", (_request, response) => {
        response.statusCode = 500;
        response.end("Browser fixture must intercept every API request");
      });
    } }],
    server: { host: "127.0.0.1", port: 43151, strictPort: false },
  });
  await server.listen();
  base = server.resolvedUrls.local[0];
});
after(async () => {
  await server?.close();
  if (cache) await rm(cache, { recursive: true, force: true });
});

const scenarios = {
  "uvp-retry": "UVP cancellation permits only a new explicit attempt with fresh readiness",
  "uvp-editor": "UVP edits, saves immutable versions and reloads recipes without execution",
  "uvp-running": "UVP explicitly starts with fresh readiness and preserves owned controls across navigation",
  "uvp-failure": "UVP stale save invalidates review without automatic retry or execution",
  "operator-retry": "explicit retry preserves the CREATED run and requests fresh blank RUN references",
  "operator-confirmation": "fresh operator form binds credentials and clears state between attempts without command replay",
  "operator-cancellation": "expired and cancelled operator requests cannot reuse credentials or automatically continue",

  navigation: "active execution remains visible after Exit, Service, Logs and Protocol navigation",
  "fresh-mount": "page reload and fresh frontend mount read and surface active backend work without commands",
  unresolved: "recovery, flushing and retained ownership survive a fresh frontend mount visibly",
  "read-failure": "initial, partial and subsequent read failures cannot claim idle or READY",
  "read-timeout": "a stalled backend read fails visibly within a bounded time",
  percentages: "connected percentages are disabled and non-applied in settings and review",
  duration: "SF mixing duration remains an enabled actual execution input",
  controls: "existing explicit Start Pause Resume Stop recovery and flush commands are preserved",
};
for (const [scenario, title] of Object.entries(scenarios)) {
  test(title, { skip: installed ? false : "Set LABFORGE_TEST_BROWSER to an installed Chrome/Chromium executable", timeout: 45000 }, async () => {
    const profile = await mkdtemp(join(tmpdir(), "labforge-ui-test-"));
    try {
      const { stdout } = await promisify(execFile)(browser, [
        "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
        "--disable-background-networking", "--no-first-run", "--no-default-browser-check",
        `--user-data-dir=${profile}`, "--dump-dom", "--virtual-time-budget=20000",
        `${base}tests/${scenario.startsWith("uvp-") ? "uvp" : "connected-execution"}.fixture.html?scenario=${scenario}`,
      ], { timeout: 40000, maxBuffer: 2 * 1024 * 1024 });
      const result = stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)?.[1];
      assert.equal(result, `PASS:${scenario}`, result ?? "Browser did not run the UI regression fixture");
    } finally {
      await rm(profile, { recursive: true, force: true });
    }
  });
}
