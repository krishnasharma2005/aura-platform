import type { Metadata, Viewport } from "next";
import { DM_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { Toaster } from "@/components/ui/toaster";

/**
 * Primary: DM Sans, for everything — headings and body alike. The brandbook
 * chooses a single family so the company has "a quieter, more unified voice".
 * Loaded as a variable font so the brand's in-between weights (500 for
 * display, 550 for H3/H4) render as real weights, never faux-bolded.
 */
const sans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-ui",
  display: "swap",
});

/** Technical: IBM Plex Mono — labels, metadata, timestamps, IDs. Never long passages. */
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Mesnium — Your business, coordinated",
  description:
    "Mesnium coordinates the front desk, sales follow-up, marketing, admin, support and store insights for your business, and asks before anything leaves it.",
};

// The product is dark-first: browser chrome follows the graphite product surface.
export const viewport: Viewport = {
  themeColor: "#202226",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${sans.variable} ${mono.variable} font-sans`}>
        <AuthProvider>
          {children}
          <Toaster />
        </AuthProvider>
      </body>
    </html>
  );
}
