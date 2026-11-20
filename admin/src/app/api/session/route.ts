import { touchSession } from "@/lib/accounts";
import { fromTheApp } from "@/lib/appKey";

/** POST {session_id, action: "ping" | "end"}: the app checking in, or signing out / closing. */
export async function POST(request: Request) {
  if (!fromTheApp(request)) return Response.json({ detail: "Not allowed." }, { status: 403 });
  const body = await request.json().catch(() => ({}));
  if (body.action !== "ping" && body.action !== "end") {
    return Response.json({ detail: "action must be ping or end" }, { status: 422 });
  }
  return Response.json({ ok: await touchSession(body.session_id, body.action === "end") });
}
