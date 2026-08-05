import type { Config } from "tailwindcss";

/**
 * Tailwind is configured as a thin mapping over the CSS variables in globals.css.
 *
 * Colours are declared as `var(--color-*)` rather than hex so there is exactly one
 * place a value can change. Writing a raw hex in a component bypasses this and
 * fails review - see rules/RULES_FRONTEND.md.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    // Replaces Tailwind's default palette entirely. An unknown colour class is
    // then a build-visible mistake instead of a silently wrong shade of grey.
    colors: {
      transparent: "transparent",
      current: "currentColor",

      primary: {
        DEFAULT: "var(--color-primary)",
        hover: "var(--color-primary-hover)",
        focus: "var(--color-primary-focus)",
        on: "var(--color-on-primary)",
      },
      canvas: "var(--color-canvas)",
      surface: {
        1: "var(--color-surface-1)",
        2: "var(--color-surface-2)",
        3: "var(--color-surface-3)",
        4: "var(--color-surface-4)",
      },
      hairline: {
        DEFAULT: "var(--color-hairline)",
        strong: "var(--color-hairline-strong)",
        tertiary: "var(--color-hairline-tertiary)",
      },
      ink: {
        DEFAULT: "var(--color-ink)",
        muted: "var(--color-ink-muted)",
        subtle: "var(--color-ink-subtle)",
        tertiary: "var(--color-ink-tertiary)",
      },
      success: "var(--color-success)",
    },

    // The DESIGN.md type scale. Each entry is [size, { lineHeight, letterSpacing }],
    // so tracking travels with the size and cannot be forgotten at a call site.
    fontSize: {
      "display-xl": ["80px", { lineHeight: "1.05", letterSpacing: "-3.0px", fontWeight: "600" }],
      "display-lg": ["56px", { lineHeight: "1.10", letterSpacing: "-1.8px", fontWeight: "600" }],
      "display-md": ["40px", { lineHeight: "1.15", letterSpacing: "-1.0px", fontWeight: "600" }],
      headline: ["28px", { lineHeight: "1.20", letterSpacing: "-0.6px", fontWeight: "600" }],
      "card-title": ["22px", { lineHeight: "1.25", letterSpacing: "-0.4px", fontWeight: "500" }],
      subhead: ["20px", { lineHeight: "1.40", letterSpacing: "-0.2px" }],
      "body-lg": ["18px", { lineHeight: "1.50", letterSpacing: "-0.1px" }],
      body: ["16px", { lineHeight: "1.50", letterSpacing: "-0.05px" }],
      "body-sm": ["14px", { lineHeight: "1.50", letterSpacing: "0" }],
      caption: ["12px", { lineHeight: "1.40", letterSpacing: "0" }],
      button: ["14px", { lineHeight: "1.20", letterSpacing: "0", fontWeight: "500" }],
      eyebrow: ["13px", { lineHeight: "1.30", letterSpacing: "0.4px", fontWeight: "500" }],
      mono: ["13px", { lineHeight: "1.50", letterSpacing: "0" }],
    },

    // 4px base unit. Named tokens only, so spacing stays on the scale.
    spacing: {
      0: "0px",
      xxs: "4px",
      xs: "8px",
      sm: "12px",
      md: "16px",
      lg: "24px",
      xl: "32px",
      xxl: "48px",
      section: "96px",
    },

    borderRadius: {
      none: "0px",
      xs: "4px",
      sm: "6px",
      md: "8px",
      lg: "12px",
      xl: "16px",
      xxl: "24px",
      pill: "9999px",
      full: "9999px",
    },

    extend: {
      fontFamily: {
        // Linear's own families are proprietary. DESIGN.md names these substitutes.
        sans: ["var(--font-inter)", "SF Pro Display", "-apple-system", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
      maxWidth: {
        content: "1280px",
      },
    },
  },
  plugins: [],
};

export default config;
