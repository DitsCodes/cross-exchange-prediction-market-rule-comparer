import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "RuleC — Cross-Platform Prediction Market Rules Comparer",
  description:
    "Paste a Polymarket or Kalshi URL and compare its settlement rules against similar markets on the other exchange.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <header className="mb-8 flex items-center justify-between">
            <a href="/" className="flex items-center gap-3">
              <span className="inline-block h-8 w-8 rounded-md bg-indigo-500" />
              <div>
                <div className="text-lg font-semibold tracking-tight">RuleC</div>
                <div className="muted text-xs">
                  Cross-platform prediction market rules comparer
                </div>
              </div>
            </a>
            <a
              className="muted text-sm hover:text-white"
              href="https://github.com"
              rel="noreferrer"
              target="_blank"
            >
              docs
            </a>
          </header>
          <main>{children}</main>
          <footer className="muted mt-16 text-center text-xs">
            Output is advisory. Always read the original market rules before trading.
          </footer>
        </div>
      </body>
    </html>
  );
}
