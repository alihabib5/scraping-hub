import { redirect } from "next/navigation";

import Mark from "@/components/Mark";
import { currentAdmin } from "@/lib/session";

import SignInForm from "./SignInForm";

export const metadata = { title: "Sign in" };

export default async function LoginPage() {
  if (await currentAdmin()) redirect("/");
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <section className="flex flex-col bg-ink-900 px-6 py-6 text-ink-100 md:w-[44%] md:max-w-xl md:justify-between md:px-12 md:py-12">
        <div className="flex items-center gap-3">
          <Mark size={36} onDark />
          <p className="font-display text-[19px] text-white">Scraping Hub</p>
        </div>
        <div className="hidden md:block">
          <h2 className="font-display text-[2.5rem] leading-[1.1] text-white">Who gets into the app, decided here.</h2>
          <ul className="mt-8 space-y-4 text-[15px] text-ink-200">
            <li className="flex gap-3">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gold-400" aria-hidden />
              Approve the accounts people request on the Windows app.
            </li>
            <li className="flex gap-3">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gold-400" aria-hidden />
              See who is signed in, from where, and for how long.
            </li>
            <li className="flex gap-3">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gold-400" aria-hidden />
              Make the encrypted credentials file after a portal password changes.
            </li>
          </ul>
        </div>
        <p className="hidden text-xs text-ink-300 md:block">For Scraping Hub administrators.</p>
      </section>

      <main className="flex flex-1 items-start justify-center bg-paper px-6 pb-16 pt-12 md:items-center md:pt-0">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-[2rem] leading-tight text-ink-900">Sign in</h1>
          <p className="mt-2 text-sm text-ink-500">Use your Scraping Hub email and password.</p>
          <SignInForm />
        </div>
      </main>
    </div>
  );
}
