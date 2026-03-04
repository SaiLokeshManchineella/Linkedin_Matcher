/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0f1a",
        neon: "#7cf6ff",
        glow: "#8b5cf6",
        glass: "rgba(255,255,255,0.08)",
      },
      boxShadow: {
        glow: "0 0 30px rgba(124, 246, 255, 0.2)",
      },
      backdropBlur: {
        md: "12px",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: ["Sora", "sans-serif"],
      },
    },
  },
  plugins: [],
};