import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NetPulse — Device Health & Impact Console",
  description: "What will fail, when, and what breaks with it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bg text-txt antialiased">{children}</body>
    </html>
  );
}
