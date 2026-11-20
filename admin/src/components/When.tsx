"use client";

import { useSyncExternalStore } from "react";

const noSubscribe = () => () => {};

/**
 * A date in the viewer's own time zone. The server runs in UTC, so formatting
 * there would show every admin the wrong hour; this formats in the browser.
 */
export default function When({ iso, time = true }: { iso: string | null; time?: boolean }) {
  const text = useSyncExternalStore(
    noSubscribe,
    () =>
      iso
        ? new Date(iso).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
            ...(time ? { hour: "numeric", minute: "2-digit" } : {}),
          })
        : "—",
    () => "", // server render: filled in on the client
  );
  return iso ? <time dateTime={iso} className="tabular whitespace-nowrap">{text}</time> : <span>—</span>;
}
