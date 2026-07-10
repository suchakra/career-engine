import type { Config } from "tailwindcss";

/**
 * Design tokens are CSS variables (see src/app/globals.css) with two value maps
 * (light / dark). Tailwind references them via var() so a single class set works
 * in both themes; dark mode is toggled by the `.dark` class on <html>.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        card: "var(--color-card)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-muted)",
        primary: {
          DEFAULT: "var(--color-primary)",
          fg: "var(--color-primary-fg)",
        },
        strong: "var(--color-strong)",
        review: "var(--color-review)",
        skipped: "var(--color-skipped)",
        error: "var(--color-error)",
      },
      borderRadius: {
        card: "12px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      ringColor: {
        focus: "var(--color-primary)",
      },
      minHeight: {
        tap: "44px",
      },
      minWidth: {
        tap: "44px",
      },
    },
  },
  plugins: [],
};

export default config;
