import type { Metadata } from "next"; // Metadata type is used to define the structure of metadata for a Next.js page or application. It provides information about the page, such as its title, description, and other relevant details.
import { Geist, Geist_Mono } from "next/font/google"; //Imports two Google fonts provided through Next.js's built-in font system
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = { //SEO things
  title: "Sales RAG",
  description: "Ask questions about the Gold warehouse",
};

export default function RootLayout({ children }: LayoutProps<"/">) { //set up the root layout for the application. It defines the overall structure and styling of the page, including the HTML and body elements, as well as the fonts used throughout the application.
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} //height full and antialiased for smoother font rendering
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
