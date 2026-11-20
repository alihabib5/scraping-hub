// next.config.ts
import type { NextConfig } from "next";

// The Windows app's console: plain static files the desktop window loads, so
// no Node server ships. Built into its own folder so it never touches the dev
// server's .next (SCRAPING_HUB_DESKTOP=1 npm run build).
const desktop = process.env.SCRAPING_HUB_DESKTOP === "1";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["localhost", "192.168.56.1"],
  ...(desktop && { output: "export", distDir: "out-desktop", typescript: { tsconfigPath: "tsconfig.desktop.json" } }),
};

export default nextConfig;
