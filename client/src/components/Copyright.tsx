/** The ownership notice shown in every footer. */
export const COPYRIGHT_OWNER = "Rizviz International Impex";

export default function Copyright({ className = "" }: { className?: string }) {
  return (
    <p className={`text-xs text-ink-400 ${className}`}>
      © {new Date().getFullYear()} {COPYRIGHT_OWNER}. All rights reserved. Scraping Hub is proprietary software;
      copying, sharing or reverse-engineering it is not permitted.
    </p>
  );
}
