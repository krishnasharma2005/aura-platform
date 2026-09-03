import type { Metadata, Viewport } from "next";
import { Familjen_Grotesk, Public_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { Toaster } from "@/components/ui/toaster";

/**
 * Display: Familjen Grotesk. Angled terminals and a slight condensation give
 * headings a calibrated, instrument-panel character without reaching for the
 * display serif that every AI-designed product uses.
 */
const display = Familjen_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

/** Body: Public Sans — humanist, civic, exceptionally legible small. */
const ui = Public_Sans({
  subsets: ["latin"],
  variable: "--font-ui",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

/** Mono: data, IDs, and micro-labels only. */
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AURA — Your business, always on",
  description:
    "AURA runs the front desk, sales follow-up, marketing, admin, support, and store insights for your business — so nothing falls through the cracks.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f4ee" },
    { media: "(prefers-color-scheme: dark)", color: "#11161c" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${display.variable} ${ui.variable} ${mono.variable} font-sans`}>
        <AuthProvider>
          {children}
          <Toaster />
        </AuthProvider>
      </body>
    </html>
  );
}
