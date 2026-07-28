import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// One .env at the repo root serves the API, the web app and docker-compose.
loadEnvConfig(path.resolve(process.cwd(), "../.."), process.env.NODE_ENV !== "production");

const nextConfig: NextConfig = {
  // Produces .next/standalone, which is what the Dockerfile ships.
  output: "standalone",
};

export default nextConfig;
