import { checkSignIn, normalEmail } from "@/lib/accounts";
import { fromTheApp } from "@/lib/appKey";

/** POST {email, password} from the app's Sign in screen. */
export async function POST(request: Request) {
  if (!fromTheApp(request)) return Response.json({ detail: "Not allowed." }, { status: 403 });
  const body = await request.json().catch(() => ({}));
  const result = await checkSignIn(body.email, body.password);
  if (result?.status === "approved") return Response.json({ email: normalEmail(body.email), name: result.name });
  if (result?.status === "pending") {
    return Response.json({ detail: "This account is waiting for an administrator to approve it." }, { status: 409 });
  }
  return Response.json({ detail: "Wrong email or password" }, { status: 401 });
}
