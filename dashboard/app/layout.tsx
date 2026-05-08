import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Devin Auto-Remediation — Apache Superset",
  description: "Static analysis remediation dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark h-full antialiased">
      <body className="min-h-full bg-[var(--background)] text-[var(--foreground)]">
        {children}
      </body>
    </html>
  );
}
