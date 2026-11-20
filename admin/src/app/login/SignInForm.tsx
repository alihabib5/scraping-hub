"use client";

import { useActionState } from "react";

import { signIn } from "@/app/actions";

const field =
  "w-full rounded-lg border border-ink-200 bg-white px-3 py-2.5 text-[15px] text-ink-900 transition hover:border-ink-300 focus:border-gold-500 focus:shadow-[0_0_0_3px_rgba(185,135,60,0.22)] focus:outline-none";

export default function SignInForm() {
  const [state, action, pending] = useActionState(signIn, null);
  return (
    <form action={action} className="mt-8 flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm font-semibold text-ink-600">
        Email
        <input
          key={state?.email}
          name="email"
          type="email"
          autoComplete="username"
          defaultValue={state?.email}
          required
          autoFocus={!state}
          spellCheck={false}
          className={field}
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm font-semibold text-ink-600">
        Password
        <input name="password" type="password" autoComplete="current-password" required autoFocus={!!state} className={field} />
      </label>
      {state?.error && (
        <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2.5 text-sm text-rose-800">
          {state.error}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="mt-1 rounded-lg bg-ink-900 py-2.5 text-[15px] font-semibold text-white transition hover:bg-ink-800 disabled:cursor-progress disabled:opacity-65"
      >
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
