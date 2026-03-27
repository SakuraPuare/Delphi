/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        dark: {
          bg: "#1a1a2e",
          surface: "#16213e",
          card: "#0f3460",
          accent: "#533483",
          text: "#e0e0e0",
          muted: "#8892a4",
          border: "#2a2a4a",
        },
      },
    },
  },
  plugins: [],
};
