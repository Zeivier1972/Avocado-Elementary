import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        avocado: { DEFAULT: "#4a7c2f", dark: "#38601f", light: "#e8f0e0" },
      },
    },
  },
  plugins: [],
};
export default config;
