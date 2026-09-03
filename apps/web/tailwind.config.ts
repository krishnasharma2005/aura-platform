import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-ui)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        // The quietest legible text tier. Use instead of `muted-foreground/NN`.
        subtle: "hsl(var(--subtle-foreground))",
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-bg))",
          foreground: "hsl(var(--sidebar-fg))",
          muted: "hsl(var(--sidebar-muted))",
          border: "hsl(var(--sidebar-border))",
          active: "hsl(var(--sidebar-active))",
        },
      },
      // Shape lock: panels 16 · cards 12 · controls/inputs 10 · pills full.
      borderRadius: {
        sm: "0.375rem",
        md: "0.625rem",
        lg: "0.75rem",
        xl: "1rem",
        "2xl": "1.25rem",
      },
      /**
       * Elevation is tinted with the foreground hue and layered — a tight
       * contact shadow plus a wide ambient one — so light surfaces read as
       * physical rather than as outlined rectangles.
       */
      boxShadow: {
        subtle: "var(--bevel), 0 1px 2px -1px hsl(var(--foreground) / 0.07)",
        card: "var(--bevel), 0 1px 2px -1px hsl(var(--foreground) / 0.08), 0 4px 12px -6px hsl(var(--foreground) / 0.10)",
        lifted:
          "var(--bevel), 0 1px 2px -1px hsl(var(--foreground) / 0.06), 0 8px 24px -10px hsl(var(--foreground) / 0.16), 0 24px 48px -24px hsl(var(--foreground) / 0.12)",
        panel:
          "var(--bevel), 0 2px 4px -2px hsl(var(--foreground) / 0.08), 0 16px 40px -16px hsl(var(--foreground) / 0.20)",
        inset: "inset 0 1px 3px 0 hsl(var(--foreground) / 0.07)",
        ringed: "0 0 0 1px hsl(var(--primary) / 0.25), 0 0 0 5px hsl(var(--primary) / 0.10)",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1.15rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.6rem" }],
        xl: ["1.25rem", { lineHeight: "1.7rem" }],
        "2xl": ["1.5rem", { lineHeight: "1.95rem" }],
        "3xl": ["1.9375rem", { lineHeight: "2.3rem" }],
        "4xl": ["2.5rem", { lineHeight: "2.85rem" }],
        "5xl": ["3.25rem", { lineHeight: "3.4rem" }],
      },
      spacing: {
        "4.5": "1.125rem",
        "9.5": "2.375rem",
        "18": "4.5rem",
        "22": "5.5rem",
      },
      transitionTimingFunction: {
        // Mass-and-spring feel. Never `linear`, never bare `ease-in-out`.
        physical: "cubic-bezier(0.32, 0.72, 0, 1)",
        settle: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // Skeletons sweep rather than blink — reads as loading, not broken.
        sweep: {
          "100%": { transform: "translateX(100%)" },
        },
        // The "working" pulse on a live tool call.
        breathe: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s cubic-bezier(0.32, 0.72, 0, 1)",
        "accordion-up": "accordion-up 0.2s cubic-bezier(0.32, 0.72, 0, 1)",
        "fade-in": "fade-in 0.24s cubic-bezier(0.16, 1, 0.3, 1)",
        sweep: "sweep 1.6s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        breathe: "breathe 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
