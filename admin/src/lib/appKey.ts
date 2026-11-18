import { timingSafeEqual } from "node:crypto";

import { env } from "@/lib/env";

/** Only an installed Scraping Hub (its credentials file carries HUB_API_KEY) may call the API. */
export function fromTheApp(request: Request): boolean {
  const given = Buffer.from(request.headers.get("x-hub-key") ?? "");
  const expected = Buffer.from(env("HUB_API_KEY"));
  return given.length === expected.length && timingSafeEqual(given, expected);
}
