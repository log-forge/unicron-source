import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig(({ mode }) => {
  return {
    base: "/unicron/",
    plugins: [tailwindcss(), reactRouter(), tsconfigPaths()],
    build: {
      chunkSizeWarningLimit: 650,
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: `http://localhost:8000`,
          changeOrigin: true,
          secure: true,
        },
      },
    },
  };
});
