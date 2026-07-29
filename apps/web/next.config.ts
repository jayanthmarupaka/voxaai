import type { NextConfig } from "next";

// The single repo-root .env is loaded by `node --env-file-if-exists` in the npm
// scripts, not here: Next caches its env before next.config.ts is evaluated, so
// loading it at this point is too late and Clerk silently falls back to keyless
// mode with a throwaway instance.
const nextConfig: NextConfig = {
  // Produces .next/standalone, which is what the Dockerfile ships.
  output: "standalone",
};

export default nextConfig;
