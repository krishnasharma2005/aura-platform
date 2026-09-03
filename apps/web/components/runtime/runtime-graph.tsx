"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "framer-motion";
import { SHARED_LAYERS, hasWebGL, type LayerId } from "@/lib/runtime-graph";
import { RuntimeGraphStatic } from "./runtime-graph-static";
import { cn } from "@/lib/utils";

/**
 * The signature surface: an interactive map of how AURA actually works.
 *
 * The whole module (three, fiber, drei — the heavy part) is code-split and
 * only requested after the page has painted, so it never blocks first paint
 * or time-to-interactive. The box it lives in has a fixed aspect ratio and is
 * filled by the static SVG from the very first frame, so nothing ever shifts:
 * the canvas cross-fades in on top of a diagram that was already correct.
 *
 * Three paths out:
 *   · prefers-reduced-motion → the static SVG, permanently. No canvas is
 *     ever requested, so we do not pay for the download either.
 *   · no WebGL → same.
 *   · WebGL fails to initialise later → we catch it and fall back.
 */
const RuntimeScene = dynamic(() => import("./runtime-scene"), {
  ssr: false,
  loading: () => null,
});

class SceneBoundary extends React.Component<
  { children: React.ReactNode; onError: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    // Never silent: if the graph falls back we want to know why, but the
    // page carries on with the static diagram either way.
    console.warn("[runtime-graph] falling back to the static diagram:", error);
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/**
 * True on a phone-width column. Both drawings need to know: the SVG switches
 * to a layout whose type survives being scaled into a 340px box, and the 3D
 * pulls its camera back to make room for the same-size label pills.
 *
 * Starts false so server and first client render agree, then corrects in an
 * effect — the diagram is decorative-first, so a single frame of the wide
 * layout is invisible next to a hydration mismatch.
 */
function useCompactViewport(): boolean {
  const [compact, setCompact] = React.useState(false);

  React.useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const sync = () => setCompact(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  return compact;
}

export function RuntimeGraph({
  activeSlugs = [],
  focusedSlug,
  onFocusAgent,
  className,
}: {
  /** Agents that have done something recently, from the real Activity feed. */
  activeSlugs?: string[];
  /** Controlled so hovering an agent card below also lights its node. */
  focusedSlug: string | null;
  onFocusAgent: (slug: string | null) => void;
  className?: string;
}) {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const compact = useCompactViewport();
  const [focusedLayer, setFocusedLayer] = React.useState<LayerId | null>(null);
  const [canRender3D, setCanRender3D] = React.useState(false);
  const [sceneReady, setSceneReady] = React.useState(false);

  React.useEffect(() => {
    // Runs after the static diagram has already rendered, so the decision to
    // load the canvas never sits in front of first paint. Deliberately not
    // requestAnimationFrame: that never fires in a background tab, which
    // would leave the graph permanently static for anyone who opens the
    // dashboard in a tab they haven't switched to yet.
    if (reduceMotion) return;
    setCanRender3D(hasWebGL());
  }, [reduceMotion]);

  const showCanvas = canRender3D && !reduceMotion;

  return (
    <div className={cn("flex flex-col", className)}>
      {/*
        Fixed aspect ratio reserves the space before anything loads. The two
        layers are absolutely positioned inside it so neither can push the
        page around.
      */}
      <div className="relative w-full overflow-hidden rounded-xl bg-gradient-to-b from-primary/[0.045] to-transparent">
        {/*
          Nearly square on a phone. The diagram is as tall as it is wide, so
          a 4:3 letterbox spends the scarce dimension (width) and throws away
          the plentiful one; squaring it up gives the orbit and the three
          plates beneath it room to be separate things.
        */}
        <div className="relative aspect-[1/1] w-full sm:aspect-[16/10] lg:aspect-[16/9]">
          <div
            aria-hidden={sceneReady && showCanvas ? true : undefined}
            className={cn(
              "absolute inset-0 transition-opacity duration-700 ease-settle",
              sceneReady && showCanvas ? "pointer-events-none opacity-0" : "opacity-100"
            )}
          >
            <RuntimeGraphStatic
              activeSlug={focusedSlug}
              layout={compact ? "compact" : "wide"}
            />
          </div>

          {showCanvas && (
            <SceneBoundary onError={() => setCanRender3D(false)}>
              <div
                className={cn(
                  "absolute inset-0 transition-opacity duration-700 ease-settle",
                  sceneReady ? "opacity-100" : "opacity-0"
                )}
              >
                <RuntimeScene
                  compact={compact}
                  activeSlugs={activeSlugs}
                  focusedSlug={focusedSlug}
                  focusedLayer={focusedLayer}
                  onFocusAgent={onFocusAgent}
                  onFocusLayer={setFocusedLayer}
                  onSelectAgent={(slug) => router.push(`/${slug}`)}
                  onReady={() => setSceneReady(true)}
                />
              </div>
            </SceneBoundary>
          )}
        </div>

        {showCanvas && (
          <p className="pointer-events-none absolute bottom-2 right-3 hidden font-mono text-[10px] uppercase tracking-[0.12em] text-subtle sm:block">
            Drag to look around
          </p>
        )}
      </div>

      {/*
        The legend is not a caption — it is a second control surface. Hovering
        a layer here lights every agent edge in the graph at once, which is
        the entire argument: all six agents reach the same memory, the same
        documents, the same accounts.
      */}
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {SHARED_LAYERS.map((layer) => {
          const isFocused = focusedLayer === layer.id;
          return (
            <button
              key={layer.id}
              type="button"
              onMouseEnter={() => setFocusedLayer(layer.id)}
              onMouseLeave={() => setFocusedLayer(null)}
              onFocus={() => setFocusedLayer(layer.id)}
              onBlur={() => setFocusedLayer(null)}
              className={cn(
                "press rounded-lg border px-3.5 py-3 text-left",
                isFocused
                  ? "border-primary/35 bg-primary/[0.06] shadow-subtle"
                  : "border-border/70 bg-card/60 hover:border-border"
              )}
            >
              <span className="flex items-center gap-2">
                <span
                  className={cn(
                    "h-1.5 w-1.5 shrink-0 rounded-full transition-colors duration-200",
                    isFocused ? "bg-primary" : "bg-primary/40"
                  )}
                />
                <span className="text-sm font-semibold text-foreground">{layer.label}</span>
              </span>
              <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
                {layer.blurb}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
