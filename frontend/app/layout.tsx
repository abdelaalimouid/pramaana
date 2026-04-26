import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PRAMAANA | Healthcare Trust Intelligence",
  description:
    "Agentic healthcare intelligence for discovering and verifying hidden facility capabilities across India.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
