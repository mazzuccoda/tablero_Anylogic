import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        borde: "#e2e8f0",
        panel: "#ffffff",
        fondo: "#f8fafc",
        acento: "#0f766e",
        alerta: "#b45309",
        critico: "#b91c1c",
        ok: "#15803d",
      },
    },
  },
  plugins: [],
};

export default config;
