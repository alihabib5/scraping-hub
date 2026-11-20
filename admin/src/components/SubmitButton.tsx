"use client";

import { useFormStatus } from "react-dom";

/** The primary action of a row form, showing that it is working while the server answers. */
export default function SubmitButton({ children, busy }: { children: React.ReactNode; busy: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      disabled={pending}
      className="whitespace-nowrap rounded-md bg-ink-900 px-3.5 py-1.5 text-sm font-semibold text-white transition duration-150 hover:bg-ink-800 disabled:cursor-progress disabled:opacity-70"
    >
      {pending ? busy : children}
    </button>
  );
}
