/** Initials in a circle: a face for each row, so a list of names reads at a glance. */
export default function Avatar({ name, tone = "ink" }: { name: string; tone?: "ink" | "gold" | "quiet" }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("") || "?";
  const look = {
    ink: "bg-ink-900 text-paper",
    gold: "bg-gold-500 text-ink-900",
    quiet: "bg-ink-100 text-ink-700",
  }[tone];
  return (
    <span
      aria-hidden
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold tracking-wide ${look}`}
    >
      {initials}
    </span>
  );
}
