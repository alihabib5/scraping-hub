import postgres from "postgres";

import { env } from "@/lib/env";

declare global {
  var hubSql: postgres.Sql | undefined; // one pool across dev hot reloads
}

const url = env("DATABASE_URL");
const local = /@(localhost|127\.0\.0\.1)[:/]/.test(url);

// Supabase's pooler (port 6543) runs in transaction mode, which cannot keep prepared statements.
export const sql = globalThis.hubSql ?? postgres(url, { ssl: local ? false : "require", prepare: false, max: 3 });
if (process.env.NODE_ENV !== "production") globalThis.hubSql = sql;
