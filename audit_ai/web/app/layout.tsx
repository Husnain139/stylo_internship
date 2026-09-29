import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Audit Document Reviewer",
  description: "Raw procurement evidence and a separate processed analysis, kept on this machine.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
