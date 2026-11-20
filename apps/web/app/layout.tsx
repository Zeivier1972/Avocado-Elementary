import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Avocado — Instructional Intelligence",
  description: "Instructional operating system for M-DCPS elementary schools.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
