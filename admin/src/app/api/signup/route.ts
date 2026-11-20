import { clientIp, Refused, requestAccount } from "@/lib/accounts";
import { fromTheApp } from "@/lib/appKey";

/** POST {name, email, password} from the app's Create account screen. */
export async function POST(request: Request) {
  if (!fromTheApp(request)) return Response.json({ detail: "Not allowed." }, { status: 403 });
  const body = await request.json().catch(() => ({}));
  try {
    const email = await requestAccount(body.name, body.email, body.password, clientIp(request));
    return Response.json({ email, status: "pending" }, { status: 201 });
  } catch (e) {
    if (e instanceof Refused) return Response.json({ detail: e.message }, { status: e.status });
    throw e;
  }
}
