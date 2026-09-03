import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { AuraLogo } from "@/components/runtime/aura-mark";
import { RuntimeGraphStatic } from "@/components/runtime/runtime-graph-static";
import { SHARED_LAYERS } from "@/lib/runtime-graph";

/**
 * First impression.
 *
 * A split: the product's own diagram on a graphite panel on the left, the
 * form on paper on the right. The panel is doing real work — it answers
 * "what is this?" before the visitor has typed anything, using the same
 * drawing they will see on the dashboard, so signing in feels like walking
 * into a place they have already been.
 *
 * No 3D here on purpose. This screen's job is to load instantly and get a
 * password typed; the interactive version earns its cost on the dashboard,
 * where exploring it is the point.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[100dvh] flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* The panel. Full height on desktop, a slim band on mobile. */}
      <aside className="relative flex flex-col justify-between overflow-hidden bg-sidebar px-6 py-6 text-sidebar-foreground sm:px-10 lg:py-12">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(ellipse_60%_80%_at_50%_0%,hsl(var(--primary)/0.20),transparent_70%)]"
        />

        <Link href="/login" className="tap-h relative z-10 inline-flex w-fit items-center">
          <AuraLogo tone="onDark" />
        </Link>

        <div className="relative z-10 hidden flex-1 flex-col justify-center py-8 lg:flex">
          <h2 className="max-w-md font-display text-4xl font-semibold leading-[1.1] tracking-[-0.03em] text-sidebar-foreground">
            Six agents that work like one team.
          </h2>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-sidebar-muted">
            Your front desk, follow-ups, marketing, admin, support, and store insights — all sharing
            what they know instead of each sitting in a separate app.
          </p>

          <div className="mt-8 max-w-lg opacity-90">
            {/*
              `onDark` is not decoration: without it the diagram draws its ink
              in `--foreground`, which in the light theme is near-black — the
              six agent labels were rendering at 1.02:1 on the graphite panel,
              i.e. invisible. The panel is graphite in both themes, so the
              tone has to be stated rather than inherited.
            */}
            <RuntimeGraphStatic className="h-auto w-full" tone="onDark" />
          </div>

          <ul className="mt-6 flex max-w-md flex-col gap-2.5">
            {SHARED_LAYERS.map((layer) => (
              <li key={layer.id} className="flex items-start gap-2.5 text-sm text-sidebar-muted">
                <span className="mt-[0.4rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span>
                  <span className="font-medium text-sidebar-foreground">{layer.label}</span>
                  {" — "}
                  {layer.blurb}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 mt-6 hidden items-start gap-2 text-xs leading-relaxed text-sidebar-muted lg:flex">
          <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0 text-primary" strokeWidth={1.75} />
          Your data stays with your business. We always show you exactly what AURA can see before
          you connect anything.
        </p>
      </aside>

      {/* The working surface. */}
      <main className="flex flex-1 flex-col items-center justify-center bg-background px-5 py-10 sm:px-8 sm:py-14">
        <div className="w-full max-w-md">{children}</div>
        <p className="mt-8 flex max-w-md items-start gap-2 text-xs leading-relaxed text-muted-foreground lg:hidden">
          <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0 text-primary" strokeWidth={1.75} />
          Your data stays with your business. We always show you exactly what AURA can see before
          you connect anything.
        </p>
      </main>
    </div>
  );
}
