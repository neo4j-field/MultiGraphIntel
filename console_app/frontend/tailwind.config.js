/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        neo: {
          slate: "#0b0e16",
          panel: "#141824",
          line: "#222634",
          ink: "#e6e9f2",
          muted: "#8a93a6",
          accent: "#4c8bf5",
          accent2: "#50e3c2",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
