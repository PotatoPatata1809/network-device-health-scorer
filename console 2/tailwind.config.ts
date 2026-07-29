import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#f6f8fa", panel: "#ffffff", line: "#d8dee4", row: "#eaeef2",
        sel: "#ddf4ff", hl: "#fff8c5", mut: "#57606a", txt: "#1f2328",
        red: "#cf222e", amber: "#9a6700", green: "#1a7f37", chip: "#eff2f5",
      },
    },
  },
  plugins: [],
} satisfies Config;
