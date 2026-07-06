/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // OpsGPT dark palette (Gemini-inspired: deep ink + violet/blue glow)
        ops: {
          bg: "#0a0a12",
          surface: "#10101b",
          panel: "#171826",
          border: "#262a3d",
          muted: "#8b90a8",
          text: "#e8eaf2",
          accent: "#6d7cff",
          "accent-hover": "#5b6bff",
          // gradient stops
          g1: "#4f8cff",
          g2: "#8b5cf6",
          g3: "#ec4899",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      backgroundImage: {
        "gemini": "linear-gradient(120deg, #4f8cff 0%, #8b5cf6 45%, #ec4899 100%)",
        "gemini-soft": "linear-gradient(120deg, rgba(79,140,255,.18), rgba(139,92,246,.18), rgba(236,72,153,.18))",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(109,124,255,.25), 0 8px 40px -8px rgba(109,124,255,.45)",
        "glow-lg": "0 0 0 1px rgba(139,92,246,.3), 0 16px 60px -10px rgba(139,92,246,.55)",
        "glow-pink": "0 10px 50px -10px rgba(236,72,153,.45)",
      },
      keyframes: {
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "bounce-dot": {
          "0%,80%,100%": { transform: "scale(0.6)", opacity: "0.4" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
        "gradient-x": {
          "0%,100%": { "background-position": "0% 50%" },
          "50%": { "background-position": "100% 50%" },
        },
        float: {
          "0%,100%": { transform: "translate(0,0) scale(1)" },
          "50%": { transform: "translate(2%,-3%) scale(1.06)" },
        },
        "glow-pulse": {
          "0%,100%": { opacity: ".5" },
          "50%": { opacity: ".85" },
        },
      },
      animation: {
        blink: "blink 1s step-start infinite",
        "fade-in": "fade-in 0.25s ease-out",
        "bounce-dot": "bounce-dot 1.4s infinite ease-in-out both",
        "gradient-x": "gradient-x 6s ease infinite",
        float: "float 14s ease-in-out infinite",
        "glow-pulse": "glow-pulse 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
