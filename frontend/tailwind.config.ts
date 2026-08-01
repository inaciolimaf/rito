import type { Config } from "tailwindcss";

// Tokens semânticos — nunca cor crua no componente (CLAUDE.md, spec 006 regra 7).
// Cada um vira `hsl(var(--x) / <alpha-value>)` para suportar opacidade (`bg-surface/50`)
// e é redefinido em `.dark` no index.css.
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "hsl(var(--surface) / <alpha-value>)",
          muted: "hsl(var(--surface-muted) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "hsl(var(--text-primary) / <alpha-value>)",
          foreground: "hsl(var(--surface) / <alpha-value>)",
        },
        muted: "hsl(var(--text-muted) / <alpha-value>)",
        default: "hsl(var(--border-default) / <alpha-value>)",
        accent: {
          DEFAULT: "hsl(var(--accent) / <alpha-value>)",
          foreground: "hsl(var(--accent-foreground) / <alpha-value>)",
        },
        danger: {
          DEFAULT: "hsl(var(--danger) / <alpha-value>)",
          foreground: "hsl(var(--danger-foreground) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "hsl(var(--warning) / <alpha-value>)",
          foreground: "hsl(var(--warning-foreground) / <alpha-value>)",
        },
        success: {
          DEFAULT: "hsl(var(--success) / <alpha-value>)",
          foreground: "hsl(var(--success-foreground) / <alpha-value>)",
        },
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
    },
  },
  plugins: [],
} satisfies Config;
