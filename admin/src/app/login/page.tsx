import { redirect } from "next/navigation";

import { currentAdmin } from "@/lib/session";

import SignInForm from "./SignInForm";

export const metadata = { title: "Sign in" };

export default async function LoginPage() {
  if (await currentAdmin()) redirect("/");
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-start px-4 pt-[14vh]">
      <p className="text-sm font-medium text-ink-600">Scraping Hub</p>
      <h1 className="font-display mt-1 text-3xl text-ink-900">Account approvals</h1>
      <p className="mt-2 text-sm text-ink-500">For administrators. Sign in with your Scraping Hub email and password.</p>
      <SignInForm />
    </main>
  );
}
