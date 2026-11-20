// Copies server/.env.example into the panel, so the Encryptor's Scraping Hub form
// follows it. Runs before every build and dev start; when the server folder is not
// there (a deploy that only has admin/), the committed copy is used as it is.
// server/tests/test_env_template_sync.py fails if the two ever differ.
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const source = new URL("../../server/.env.example", import.meta.url);
const target = new URL("../src/lib/env-template.ts", import.meta.url);

if (!existsSync(source)) {
  console.log("server/.env.example not found; keeping the committed env template.");
} else {
  const text = readFileSync(source, "utf8").replace(/\r\n/g, "\n");
  const out = `// Generated from server/.env.example by scripts/sync-env-template.mjs. Do not edit by hand.\nexport const ENV_EXAMPLE = ${JSON.stringify(text)};\n`;
  const before = existsSync(target) ? readFileSync(target, "utf8") : "";
  if (before !== out) {
    writeFileSync(target, out);
    console.log("env template updated from server/.env.example.");
  }
}
