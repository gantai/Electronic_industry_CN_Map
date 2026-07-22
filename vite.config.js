import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base:"./" → 相对路径构建:GitHub Pages 项目页、自定义域名或任意子路径均可直接部署
export default defineConfig({
  base: "./",
  plugins: [react()],
});
