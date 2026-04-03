import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        strix: {
          // Light mode palette
          primary: "#006B94",
          secondary: "#00D0FC",
          tertiary: "#0B71D1",
          neutral: "#4B7F8B",
          // Dark mode palette
          cyan: "#00F2FF",
          purple: "#8A2BE2",
          // Backgrounds
          "bg-dark": "#0B0E14",
          "bg-dark-card": "#111827",
          "bg-dark-surface": "#161B26",
          "bg-light": "#F0F9FC",
          "bg-light-card": "#FFFFFF",
          "bg-light-surface": "#E8F4F8",
          // Semantic
          "accent-teal": "#0D9488",
          "accent-cyan": "#00F2FF",
          danger: "#EF4444",
          warning: "#F59E0B",
          success: "#10B981",
          info: "#3B82F6",
        },
        // Sidebar
        sidebar: {
          bg: "#0A1628",
          hover: "#112240",
          active: "#00F2FF",
          text: "#94A3B8",
          "text-active": "#FFFFFF",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        heading: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["Liberation Mono", "JetBrains Mono", "Fira Code", "monospace"],
      },
      borderRadius: {
        lg: "0.75rem",
        md: "0.5rem",
        sm: "0.25rem",
      },
      boxShadow: {
        "strix-glow": "0 0 20px rgba(0, 242, 255, 0.15)",
        "strix-card": "0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06)",
      },
    },
  },
  plugins: [],
}

export default config
