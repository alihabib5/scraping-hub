"use client";

import { useEffect, useState } from "react";
import { useFormStatus } from "react-dom";

/**
 * A submit button that asks once before an action that cannot be undone:
 * the first click turns it into "Confirm …" for a few seconds, the second
 * submits its form. Escape or waiting backs out.
 */
export default function ConfirmButton({ label, confirmLabel, tone = "danger" }: {
  label: string;
  confirmLabel: string;
  tone?: "danger" | "quiet";
}) {
  const [armed, setArmed] = useState(false);
  const { pending } = useFormStatus();

  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setArmed(false);
    document.addEventListener("keydown", esc);
    return () => {
      clearTimeout(t);
      document.removeEventListener("keydown", esc);
    };
  }, [armed]);

  const rest = tone === "danger"
    ? "text-rose-700 hover:bg-rose-50"
    : "text-ink-600 hover:bg-ink-50 hover:text-ink-900";
  const hot = tone === "danger" ? "bg-rose-700 text-white hover:bg-rose-800" : "bg-ink-700 text-white hover:bg-ink-800";

  return (
    <button
      type={armed ? "submit" : "button"}
      disabled={pending}
      onClick={(e) => {
        if (!armed) {
          e.preventDefault();
          setArmed(true);
        }
      }}
      className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition duration-150 disabled:cursor-progress disabled:opacity-60 ${armed ? hot : rest}`}
    >
      {pending ? "Working…" : armed ? confirmLabel : label}
    </button>
  );
}
