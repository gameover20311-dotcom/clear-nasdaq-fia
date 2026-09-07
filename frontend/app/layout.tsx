import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CLEAR NASDAQ — Obsidian Live Cockpit",
  description: "Evidence-first NQ 4–8H research cockpit with fail-closed live data truth.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
