/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { execSync } from "node:child_process";
import { fileURLToPath, URL } from "node:url";

// Which build this is: the commit (CI sets GITHUB_SHA) and when it was built. The desk compares it with the
// deployed dist/version.json, so a home-screen app or a long-open tab can't stay on an old version unnoticed.
function commit(): string {
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA.slice(0, 7);
  try {
    return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "local";
  }
}
const BUILD = { id: `${commit()}-${Date.now().toString(36)}`, at: new Date().toISOString() };

function versionFile(): Plugin {
  return {
    name: "pbs-version",
    apply: "build",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "version.json", source: JSON.stringify(BUILD) });
    },
  };
}

// base "./" + hash routing: the desk works under any path (GitHub Pages, Cloudflare Pages, a local file server).
export default defineConfig({
  base: "./",
  define: { __BUILD__: JSON.stringify(BUILD) },
  plugins: [react(), tailwindcss(), versionFile()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 900 },
  server: { port: 5173 },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
