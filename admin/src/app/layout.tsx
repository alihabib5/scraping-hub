import type { Metadata } from "next";
import { Fraunces, Geist } from "next/font/google";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const displaySerif = Fraunces({ variable: "--font-display-serif", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Accounts · Scraping Hub", template: "%s · Scraping Hub" },
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${displaySerif.variable} h-full antialiased`}>
      <body className="min-h-full bg-paper text-ink-900">{children}</body>
    </html>
  );
}
