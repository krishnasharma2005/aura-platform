import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { MesniumLogo } from "@/components/brand/mesnium-logo";
import { SHARED_CONTEXT } from "@/lib/agent-connections";

/**
 * First impression.
 *
 * A split: a calm graphite panel that says what the product is, and the form
 * beside it. No diagram and no decoration; the panel's job is to answer "what
 * is this?" in two sentences before the visitor has typed anything, then get
 * out of the way of the password.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[100dvh] flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* The panel. Full height on desktop, a slim band on mobile. */}
      <aside className="relative flex flex-col justify-between overflow-hidden bg-sidebar px-6 py-6 text-sidebar-foreground sm:px-10 lg:py-12">
        <Link href="/login" className="tap-h relative z-10 inline-flex w-fit items-center">
          <MesniumLogo tone="onDark" className="h-8 w-auto" />
        </Link>

        <div className="relative z-10 hidden flex-1 flex-col justify-center py-8 lg:flex">
          <h2 className="max-w-md font-display text-4xl font-semibold leading-[1.1] tracking-[-0.03em] text-sidebar-foreground">
            Your business, coordinated.
          </h2>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-sidebar-muted">
            Mesnium carries work from intention to accomplished: it understands your request, coordinates the
            tools you already use, and asks before anything leaves your business.
          </p>

          <ul className="mt-8 flex max-w-md flex-col gap-3">
            {SHARED_CONTEXT.map((item) => (
              <li key={item.id} className="flex items-start gap-2.5 text-sm text-sidebar-muted">
                <span className="mt-[0.4rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span>
                  <span className="font-medium text-sidebar-foreground">{item.label}</span>
                  {" — "}
                  {item.blurb}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 mt-6 hidden items-start gap-2 text-xs leading-relaxed text-sidebar-muted lg:flex">
          <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0 text-primary-ink" strokeWidth={1.5} />
          Your data stays with your business. We always show you exactly what Mesnium can see before
          you connect anything.
        </p>
      </aside>

      {/* The working surface. */}
      <main className="flex flex-1 flex-col items-center justify-center bg-background px-5 py-10 sm:px-8 sm:py-14">
        <div className="w-full max-w-md">{children}</div>
        <p className="mt-8 flex max-w-md items-start gap-2 text-xs leading-relaxed text-muted-foreground lg:hidden">
          <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0 text-primary-ink" strokeWidth={1.5} />
          Your data stays with your business. We always show you exactly what Mesnium can see before
          you connect anything.
        </p>
      </main>
    </div>
  );
}
