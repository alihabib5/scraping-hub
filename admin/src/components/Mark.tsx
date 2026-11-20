/** The Scraping Hub mark: rows of a list, the found one in gold. Same drawing as the app's sign-in screen. */
export default function Mark({ size = 32, onDark = false }: { size?: number; onDark?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden className="shrink-0">
      <rect width="40" height="40" rx="10" fill={onDark ? "#faf9f6" : "#0b1f3a"} />
      <path d="M11 14.5h18M11 20h12M11 25.5h15" stroke={onDark ? "#0b1f3a" : "#faf9f6"} strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="28.5" cy="25.5" r="2.6" fill="#b9873c" />
    </svg>
  );
}
