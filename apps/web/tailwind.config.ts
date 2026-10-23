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
        // One family: headings use DM Sans too (the brandbook's single-voice rule).
        display: ["var(--font-ui)", "system-ui", "sans-serif"],
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
          // For text: the fill colour fails contrast as small text on dark surfaces.
          ink: "hsl(var(--primary-ink))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
          // For text: the fill colour fails contrast as small text on dark surfaces.
          ink: "hsl(var(--destructive-ink))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
          // For text: the fill colour fails contrast as small text on dark surfaces.
          ink: "hsl(var(--warning-ink))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
          // For text: the fill colour fails contrast as small text on dark surfaces.
          ink: "hsl(var(--success-ink))",
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
      // Brandbook radius scale: small controls 4 · cards 8 · app tiles 16 · pills full.
      // `md` is the control size (buttons, inputs, chips), `lg`/`xl` the card size.
      borderRadius: {
        sm: "4px",
        md: "4px",
        lg: "8px",
        xl: "8px",
        "2xl": "16px",
      },
      /**
       * Matte. Cards are separated by a hairline, not a shadow; elevation is
       * reserved for dialogs and floating controls (brandbook p. 21).
       */
      boxShadow: {
        subtle: "none",
        card: "none",
        lifted: "var(--elevation)",
        panel: "var(--elevation)",
        inset: "var(--inset-shadow)",
        ringed: "0 0 0 2px hsl(var(--ring) / 0.5)",
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
      // Brandbook motion (p. 17-18): four tempos and one entrance curve. No
      // bounce, overshoot or springs. `physical`/`settle` are kept as aliases so
      // existing classes resolve to the same brand curve.
      transitionDuration: {
        respond: "160ms",
        reveal: "240ms",
        resolve: "480ms",
        introduce: "640ms",
      },
      transitionTimingFunction: {
        brand: "cubic-bezier(0.22, 1, 0.36, 1)",
        physical: "cubic-bezier(0.22, 1, 0.36, 1)",
        settle: "cubic-bezier(0.22, 1, 0.36, 1)",
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
      },
      animation: {
        "accordion-down": "accordion-down 240ms cubic-bezier(0.22, 1, 0.36, 1)",
        "accordion-up": "accordion-up 240ms cubic-bezier(0.22, 1, 0.36, 1)",
        "fade-in": "fade-in 240ms cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
