/** The Rizviz "RV" mark (public/rizviz-mark.png, made by installer/make_logo.py). */
export default function Logo({ className = "h-9 w-9" }: { className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static export (desktop app): next/image optimisation is unavailable
    <img src="/rizviz-mark.png" alt="Rizviz" className={`${className} shrink-0 object-contain`} draggable={false} />
  );
}
