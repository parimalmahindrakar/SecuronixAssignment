import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Inside Docker the API is reachable as http://backend:8000 (set via API_URL in docker-compose.yml)
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": process.env.API_URL || "http://localhost:8000" } },
});
