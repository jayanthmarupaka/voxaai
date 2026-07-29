/**
 * Runs the Next.js CLI with the single repo-root .env already loaded.
 *
 * Why this exists: the root .env serves the API, the web app and docker-compose,
 * but Next only looks for .env files inside apps/web. Calling loadEnvConfig from
 * next.config.ts is too late — Next has already resolved its env by then, and
 * @clerk/nextjs silently starts a throwaway "keyless" instance instead of using
 * the real keys. Node's --env-file flag can't be used either, because Next
 * copies execArgv into NODE_OPTIONS for its workers, where that flag is banned.
 *
 * Loading the env here, before Next is spawned, means the child inherits it.
 * If there is no root .env (CI, Docker) the real environment is used unchanged.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// @next/env is CommonJS, so it has no named ESM exports.
import nextEnv from "@next/env";

const { loadEnvConfig } = nextEnv;

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webDir, "../..");
const command = process.argv[2];

if (existsSync(path.join(repoRoot, ".env"))) {
  loadEnvConfig(repoRoot, command === "dev");
}

const result = spawnSync(
  process.execPath,
  [path.join(webDir, "node_modules", "next", "dist", "bin", "next"), ...process.argv.slice(2)],
  { stdio: "inherit", cwd: webDir },
);

process.exit(result.status ?? 1);
