import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CLEAR NASDAQ — FIA Research Cockpit",
  description: "Evidence-first NASDAQ research and validation dashboard.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
