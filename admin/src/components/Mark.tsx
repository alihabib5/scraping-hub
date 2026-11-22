/**
 * The Rizviz "RV" mark (public/rizviz-mark.png, made by installer/make_logo.py), the same as the app's.
 * On a dark background it sits on a light tile, because the mark's navy would disappear on navy.
 */
export default function Mark({ size = 32, onDark = false }: { size?: number; onDark?: boolean }) {
  // eslint-disable-next-line @next/next/no-img-element -- a small static mark; next/image adds nothing here
  const img = <img src="/rizviz-mark.png" alt="Rizviz" width={size} height={size} draggable={false} className="shrink-0" />;
  if (!onDark) return img;
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-[10px] bg-[#faf9f6]"
      style={{ width: size, height: size, padding: Math.round(size * 0.1) }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- see above */}
      <img src="/rizviz-mark.png" alt="Rizviz" className="h-full w-full object-contain" draggable={false} />
    </span>
  );
}
