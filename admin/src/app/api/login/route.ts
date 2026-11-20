import { checkSignIn, clientIp, normalEmail, startSession } from "@/lib/accounts";
import { fromTheApp } from "@/lib/appKey";

/** POST {email, password} from the app's Sign in screen. A success opens a session the dashboard shows. */
export async function POST(request: Request) {
  if (!fromTheApp(request)) return Response.json({ detail: "Not allowed." }, { status: 403 });
  const body = await request.json().catch(() => ({}));
  const result = await checkSignIn(body.email, body.password);
  if (result?.status === "approved") {
    const email = normalEmail(body.email);
    return Response.json({ email, name: result.name, session_id: await startSession(email, clientIp(request)) });
  }
  if (result?.status === "pending") {
    return Response.json({ detail: "This account is waiting for an administrator to approve it." }, { status: 409 });
  }
  return Response.json({ detail: "Wrong email or password" }, { status: 401 });
}
