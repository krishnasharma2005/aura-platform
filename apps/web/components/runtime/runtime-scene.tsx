"use client";

import * as React from "react";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import {
  GRAPH_NODES,
  SHARED_LAYERS,
  edgePoints,
  nodePosition,
  pointOnEdge,
  themeColor,
  type LayerId,
} from "@/lib/runtime-graph";

/**
 * The runtime graph, in three dimensions.
 *
 * What it argues: AURA is not six tools in a sidebar. It is one runtime with
 * six faces. The core in the middle is that runtime; the three plates beneath
 * it are the memory, the documents, and the connected accounts that all six
 * agents share; the six nodes on the orbit are the agents themselves, each
 * wired down through the shared foundation and into the core.
 *
 * What it teaches on interaction:
 *   · Hover an agent  → its edge lights and all three plates light with it.
 *                       One agent touches every shared layer.
 *   · Hover a plate   → all six edges light at once.
 *                       Every agent touches this same layer.
 *   · Real activity   → an agent's edge carries a brighter, faster pulse into
 *                       the core. This is driven by the actual Activity feed,
 *                       not a timer, so what you see happened.
 *   · Click an agent  → opens that agent.
 *
 * Performance: ~3k triangles, no shadow maps, no post-processing, no external
 * assets to fetch. Capped at 1.75x device pixel ratio. It holds 60fps on
 * integrated graphics, and the whole module is code-split out of first paint.
 */

interface Palette {
  core: string;
  edge: string;
  node: string;
  plate: string;
}

/** Slow, continuous drift so the scene reads as an object, not a picture. */
const DRIFT_SPEED = 0.055;

/**
 * Where the assembly sits in world space. Everything rotates *around* this
 * point, so it is also the fixed screen anchor the labels push away from.
 */
const GROUP_Y = 0.42;
const CORE_WORLD = new THREE.Vector3(0, GROUP_Y, 0);
/** Radius of the machined shell, plus the margin a label pill needs. */
const CORE_CLEAR_UNITS = 0.86;

const _node = new THREE.Vector3();
const _core = new THREE.Vector3();

/**
 * The projected radius, in CSS pixels, of a sphere of `units` world-radius
 * sitting at the centre of the scene. Used to work out how far a label has to
 * move before it is off the core.
 */
function screenRadius(camera: THREE.Camera, height: number, units: number): number {
  const cam = camera as THREE.PerspectiveCamera;
  const dist = cam.position.distanceTo(CORE_WORLD);
  const halfFov = (cam.fov * Math.PI) / 360;
  return (units / (2 * dist * Math.tan(halfFov))) * height;
}

function CoreAssembly({ palette, energy }: { palette: Palette; energy: number }) {
  const shellRef = React.useRef<THREE.Mesh>(null);
  const innerRef = React.useRef<THREE.Mesh>(null);

  useFrame((state, delta) => {
    if (shellRef.current) {
      shellRef.current.rotation.y += delta * 0.14;
      shellRef.current.rotation.x += delta * 0.05;
    }
    if (innerRef.current) {
      // The core breathes; it beats harder when agents are working.
      const t = state.clock.elapsedTime;
      const beat = 1 + Math.sin(t * 1.4) * 0.035 + energy * 0.14;
      innerRef.current.scale.setScalar(beat);
      const mat = innerRef.current.material as THREE.MeshStandardMaterial;
      mat.emissiveIntensity = 0.7 + energy * 1.1 + Math.sin(t * 1.4) * 0.08;
    }
  });

  return (
    <group>
      {/* Machined outer shell — faceted, open, so the lit core shows through. */}
      <mesh ref={shellRef}>
        <icosahedronGeometry args={[0.78, 1]} />
        <meshStandardMaterial
          color={palette.core}
          wireframe
          transparent
          opacity={0.5}
          roughness={0.4}
        />
      </mesh>
      {/* The runtime itself. */}
      <mesh ref={innerRef}>
        <icosahedronGeometry args={[0.34, 2]} />
        <meshStandardMaterial
          color={palette.core}
          emissive={palette.core}
          emissiveIntensity={0.8}
          roughness={0.25}
          metalness={0.1}
        />
      </mesh>
      {/*
        Screen-space label: constant size regardless of camera distance. It
        sits well clear of the sphere because an agent label that has been
        pushed off the core lands just outside the shell — at the old 1.15 the
        two collided every time an agent drifted to the back of the orbit.
      */}
      <Html center position={[0, 1.66, 0]} zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
        <span className="select-none whitespace-nowrap rounded-full border border-primary/25 bg-card/90 px-2.5 py-1 font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-primary shadow-subtle">
          One runtime
        </span>
      </Html>
    </group>
  );
}

function LayerPlate({
  layer,
  palette,
  highlighted,
  onHover,
}: {
  layer: (typeof SHARED_LAYERS)[number];
  palette: Palette;
  highlighted: boolean;
  onHover: (id: LayerId | null) => void;
}) {
  const ref = React.useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    if (!ref.current) return;
    ref.current.rotation.z += delta * 0.08;
    const mat = ref.current.material as THREE.MeshStandardMaterial;
    const target = highlighted ? 1 : 0.6;
    mat.opacity += (target - mat.opacity) * Math.min(1, delta * 9);
    mat.emissiveIntensity += ((highlighted ? 1.1 : 0.18) - mat.emissiveIntensity) * Math.min(1, delta * 9);
  });

  return (
    <group position={[0, layer.y, 0]}>
      <mesh
        ref={ref}
        rotation={[Math.PI / 2, 0, 0]}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          onHover(layer.id);
        }}
        onPointerOut={() => onHover(null)}
      >
        <torusGeometry args={[layer.radius, 0.028, 8, 96]} />
        <meshStandardMaterial
          color={palette.plate}
          emissive={palette.core}
          emissiveIntensity={0.18}
          transparent
          opacity={0.42}
          roughness={0.5}
        />
      </mesh>
    </group>
  );
}

function AgentEdge({
  from,
  palette,
  intensity,
}: {
  from: [number, number, number];
  palette: Palette;
  intensity: number;
}) {
  const points = React.useMemo(() => edgePoints(from), [from]);
  return (
    <Line
      points={points}
      color={intensity > 0.6 ? palette.core : palette.edge}
      lineWidth={intensity > 0.6 ? 2.1 : 1.1}
      transparent
      opacity={0.2 + intensity * 0.75}
    />
  );
}

/**
 * A packet of work moving from an agent into the shared core. Ambient pulses
 * run slowly on every edge; a pulse on an agent that has just done something
 * real runs faster and brighter.
 */
function EdgePulse({
  from,
  palette,
  speed,
  brightness,
  phase,
}: {
  from: [number, number, number];
  palette: Palette;
  speed: number;
  brightness: number;
  phase: number;
}) {
  const ref = React.useRef<THREE.Mesh>(null);
  const t = React.useRef(phase);

  useFrame((_, delta) => {
    if (!ref.current) return;
    t.current = (t.current + delta * speed) % 1;
    const [x, y, z] = pointOnEdge(from, t.current);
    ref.current.position.set(x, y, z);
    // Fade in at the node, out at the core, so it reads as travel not orbit.
    const fade = Math.sin(t.current * Math.PI);
    ref.current.scale.setScalar(0.055 + fade * 0.05 * brightness);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = fade * brightness;
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1, 10, 10]} />
      <meshBasicMaterial color={palette.core} transparent opacity={0} />
    </mesh>
  );
}

/**
 * An agent, and its label.
 *
 * The label is the fiddly part. It used to hang at a fixed local offset above
 * the node, which meant that as the assembly drifted, whichever agent happened
 * to be at the front or the back of the orbit projected straight onto the core
 * — "Receptionist" and "Assistant" sat on the sphere and on each other, and
 * "Sales"/"Marketing" piled up on the right. A world-space offset cannot fix
 * that, because the collision happens after projection.
 *
 * So placement is resolved in screen space, every frame, with two rules:
 *
 *   1. **Clear the core.** Project the node and the core. If the label lands
 *      inside the core's projected disc, slide it straight out along the
 *      node→core axis until it clears. Only labels that would overlap move,
 *      so an agent out at the edge of the orbit keeps its label pinned to it.
 *   2. **Alternate the tier.** Even-indexed agents sit above their node, odd
 *      ones below. Nodes that crowd on screen are always neighbours on the
 *      orbit (i±1) or opposite each other across it (i±3), and both of those
 *      pairs differ in parity — so crowding separates vertically instead of
 *      stacking.
 *
 * Depth ordering is left to drei, which maps camera distance into
 * `zIndexRange`, so a near label always covers a far one rather than the two
 * interleaving. The pill is opaque for the same reason.
 */
function AgentNode({
  index,
  label,
  palette,
  focused,
  dimmed,
  active,
  compact,
  onHover,
  onSelect,
}: {
  index: number;
  label: string;
  palette: Palette;
  focused: boolean;
  dimmed: boolean;
  active: boolean;
  /** Narrow viewport: smaller pills and tighter offsets. */
  compact: boolean;
  onHover: () => void;
  onBlur?: () => void;
  onSelect: () => void;
}) {
  const position = React.useMemo(() => nodePosition(index), [index]);
  const ref = React.useRef<THREE.Mesh>(null);
  const groupRef = React.useRef<THREE.Group>(null);
  const labelRef = React.useRef<HTMLSpanElement>(null);

  const tier = index % 2 === 0 ? -1 : 1;

  useFrame((state, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.4;
      const target = focused ? 1.5 : active ? 1.25 : 1;
      const s = ref.current.scale.x;
      ref.current.scale.setScalar(s + (target - s) * Math.min(1, delta * 10));
      const mat = ref.current.material as THREE.MeshStandardMaterial;
      const glow = focused
        ? 1.5
        : active
        ? 0.9 + Math.sin(state.clock.elapsedTime * 3) * 0.25
        : 0.22;
      mat.emissiveIntensity += (glow - mat.emissiveIntensity) * Math.min(1, delta * 9);
    }

    const el = labelRef.current;
    const group = groupRef.current;
    if (!el || !group) return;

    const { camera, size } = state;
    group.getWorldPosition(_node).project(camera);
    _core.copy(CORE_WORLD).project(camera);

    // NDC → CSS pixels, relative to the core.
    const dx = ((_node.x - _core.x) * size.width) / 2;
    const dy = (-(_node.y - _core.y) * size.height) / 2;
    const dist = Math.hypot(dx, dy) || 1;

    const clear = screenRadius(camera, size.height, CORE_CLEAR_UNITS) + (compact ? 14 : 20);
    const push = dist < clear ? clear - dist : 0;
    const lift = (compact ? 17 : 21) * tier;

    el.style.transform = `translate(${((dx / dist) * push).toFixed(1)}px, ${(
      (dy / dist) * push +
      lift
    ).toFixed(1)}px)`;
  });

  return (
    <group ref={groupRef} position={position}>
      <mesh
        ref={ref}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          onHover();
        }}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onSelect();
        }}
      >
        <octahedronGeometry args={[0.15, 0]} />
        <meshStandardMaterial
          color={palette.node}
          emissive={palette.core}
          emissiveIntensity={0.22}
          roughness={0.32}
          metalness={0.35}
        />
      </mesh>
      <Html center zIndexRange={[8, 0]} style={{ pointerEvents: "none" }} position={[0, 0, 0]}>
        <span
          ref={labelRef}
          className={`inline-block select-none whitespace-nowrap rounded-full border px-2 py-0.5 font-semibold transition-colors duration-200 ${
            compact ? "text-[10px]" : "text-[11px]"
          } ${
            dimmed
              ? "border-border/40 bg-card/70 text-subtle"
              : focused
              ? "border-primary/40 bg-card text-primary shadow-subtle"
              : "border-border/70 bg-card text-foreground shadow-subtle"
          }`}
        >
          {label}
        </span>
      </Html>
    </group>
  );
}

interface SceneProps {
  /** Narrow viewport: pull the camera back and shrink the labels. */
  compact?: boolean;
  activeSlugs: string[];
  focusedSlug: string | null;
  /** Lifted so the legend below the canvas can drive the highlight too. */
  focusedLayer: LayerId | null;
  onFocusAgent: (slug: string | null) => void;
  onFocusLayer: (layer: LayerId | null) => void;
  onSelectAgent: (slug: string) => void;
}

function Scene({
  compact = false,
  activeSlugs,
  focusedSlug,
  focusedLayer: hoveredLayer,
  onFocusAgent,
  onFocusLayer: setHoveredLayer,
  onSelectAgent,
}: SceneProps) {
  const groupRef = React.useRef<THREE.Group>(null);
  const [palette, setPalette] = React.useState<Palette>({
    core: "#14544e",
    edge: "#94a39e",
    node: "#2b3339",
    plate: "#6f7d79",
  });

  React.useEffect(() => {
    setPalette({
      core: themeColor("--graph-core", "#14544e"),
      edge: themeColor("--graph-edge", "#94a39e"),
      node: themeColor("--graph-core", "#2b3339"),
      plate: themeColor("--graph-edge", "#6f7d79"),
    });
  }, []);

  useFrame((_, delta) => {
    if (groupRef.current && !focusedSlug && !hoveredLayer) {
      groupRef.current.rotation.y += delta * DRIFT_SPEED;
    }
  });

  const energy = Math.min(1, activeSlugs.length / 3);

  return (
    <>
      <ambientLight intensity={1.15} />
      <directionalLight position={[4, 6, 4]} intensity={1.5} />
      <directionalLight position={[-5, -2, -4]} intensity={0.45} />

      <group ref={groupRef} position={[0, 0.42, 0]}>
        <CoreAssembly palette={palette} energy={energy} />

        {SHARED_LAYERS.map((layer) => (
          <LayerPlate
            key={layer.id}
            layer={layer}
            palette={palette}
            // A focused agent lights every plate: one agent uses all three.
            // A hovered plate lights only itself while every edge lights up.
            highlighted={hoveredLayer === layer.id || Boolean(focusedSlug)}
            onHover={setHoveredLayer}
          />
        ))}

        {/* The spine: the core sitting on the shared foundation. */}
        <Line
          points={[
            [0, 0, 0],
            [0, SHARED_LAYERS[SHARED_LAYERS.length - 1].y, 0],
          ]}
          color={palette.core}
          lineWidth={1.4}
          transparent
          opacity={hoveredLayer ? 0.85 : 0.35}
        />

        {GRAPH_NODES.map((node, i) => {
          const from = nodePosition(i);
          const isActive = activeSlugs.includes(node.slug);
          const isFocused = focusedSlug === node.slug;
          // Hovering a shared layer lights every edge at once — the whole
          // point: all six agents reach the same layer.
          const intensity = hoveredLayer
            ? 0.85
            : isFocused
            ? 1
            : focusedSlug
            ? 0.06
            : isActive
            ? 0.7
            : 0.28;
          return (
            <React.Fragment key={node.slug}>
              <AgentEdge from={from} palette={palette} intensity={intensity} />
              <EdgePulse
                from={from}
                palette={palette}
                speed={isActive ? 0.55 : 0.16}
                brightness={hoveredLayer ? 0.9 : isFocused ? 1 : focusedSlug ? 0.05 : isActive ? 0.85 : 0.3}
                phase={i / GRAPH_NODES.length}
              />
              <AgentNode
                index={i}
                label={node.label}
                palette={palette}
                focused={isFocused}
                dimmed={Boolean(focusedSlug) && !isFocused}
                active={isActive}
                compact={compact}
                onHover={() => onFocusAgent(node.slug)}
                onSelect={() => onSelectAgent(node.slug)}
              />
            </React.Fragment>
          );
        })}
      </group>

      <OrbitControls
        enablePan={false}
        enableZoom={false}
        autoRotate={false}
        minPolarAngle={Math.PI * 0.24}
        maxPolarAngle={Math.PI * 0.62}
        rotateSpeed={0.55}
        dampingFactor={0.08}
        enableDamping
      />
    </>
  );
}

export default function RuntimeScene(props: SceneProps & { onReady?: () => void }) {
  const { onReady, ...sceneProps } = props;

  return (
    <Canvas
      // Transparent so the page's paper ground shows through — the graph is
      // an object sitting on the page, not a video playing in a box.
      gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
      dpr={[1, 1.75]}
      /*
       * The labels are screen-space pills at a fixed pixel size, so they do
       * not shrink with the viewport — on a phone column the orbit has to be
       * pulled back to buy the room they need. Framing, not a zoom level:
       * the assembly occupies the same fraction of the box either way.
       */
      camera={
        sceneProps.compact
          ? { position: [0, 2.5, 10.2], fov: 40 }
          : { position: [0, 2.1, 7.4], fov: 40 }
      }
      onPointerMissed={() => sceneProps.onFocusAgent(null)}
      onCreated={() => onReady?.()}
      style={{ touchAction: "pan-y" }}
    >
      <Scene {...sceneProps} />
    </Canvas>
  );
}
