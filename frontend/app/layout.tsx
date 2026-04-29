import "./globals.css";
import type { Metadata } from "next";
import { Inter_Tight, Instrument_Serif } from "next/font/google";

const sans = Inter_Tight({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const serif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-serif",
});

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
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body className="min-h-screen antialiased">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <header className="mb-12 flex items-center justify-between">
            <a href="/" className="group flex items-center gap-3 rounded-md p-1 -m-1">
              <span
                aria-hidden
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--border)] bg-[var(--panel-2)] font-serif text-xl leading-none text-[var(--accent)]"
              >
                R
              </span>
              <div>
                <div className="text-base font-semibold tracking-tight">RuleC</div>
                <div className="muted text-xs">
                  Cross-platform prediction market rules comparer
                </div>
              </div>
            </a>
            <a
              className="muted hover:text-white inline-flex h-11 items-center px-3 text-sm rounded-md focus-ring"
              href="https://github.com"
              rel="noreferrer"
              target="_blank"
            >
              docs
            </a>
          </header>
          <main>{children}</main>
          <footer className="muted mt-20 text-xs">
            Output is advisory. Always read the original market rules before trading.
          </footer>
        </div>
      </body>
    </html>
  );
}
