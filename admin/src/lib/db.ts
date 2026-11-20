import postgres from "postgres";

import { env } from "@/lib/env";

declare global {
  var hubSql: postgres.Sql | undefined; // one pool across dev hot reloads
}

/** The pool, made on first use: `next build` loads this module without DATABASE_URL, and must still build. */
function pool(): postgres.Sql {
  if (!globalThis.hubSql) {
    const url = env("DATABASE_URL");
    const local = /@(localhost|127\.0\.0\.1)[:/]/.test(url);
    // Supabase's pooler (port 6543) runs in transaction mode, which cannot keep prepared statements.
    globalThis.hubSql = postgres(url, { ssl: local ? false : "require", prepare: false, max: 3 });
  }
  return globalThis.hubSql;
}

/** Used as a tagged template (sql`select …`), exactly like the pool itself. */
export const sql = ((strings: TemplateStringsArray, ...values: never[]) => pool()(strings, ...values)) as unknown as postgres.Sql;
