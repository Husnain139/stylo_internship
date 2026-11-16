import type { Metadata } from "next";
import { SessionProvider } from "@/components/session";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "HR Desk",
  description: "Ask a question about Stylo policies and see the answer in plain language.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>
          <Shell>{children}</Shell>
        </SessionProvider>
      </body>
    </html>
  );
}
