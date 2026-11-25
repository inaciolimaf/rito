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
        // Texto sobre `bg-primary`: segue o tema sem inverter (ver docs/frontend-identity.md).
        "on-primary": "hsl(var(--surface) / <alpha-value>)",
        // Véu atrás de diálogos e gavetas: preto no claro e no escuro, nunca a cor do texto.
        overlay: "hsl(var(--overlay) / <alpha-value>)",
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
      // Escala tipográfica: só estes dois tamanhos extras. Os demais vêm do padrão do Tailwind.
      // Sem `text-[NNpx]` no componente (docs/frontend-identity.md, seção de tipografia).
      fontSize: {
        micro: "10px",
        caption: "11px",
      },
    },
  },
  plugins: [],
} satisfies Config;
