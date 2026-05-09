import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, process.cwd(), "");
    var backendPort = env.VITE_BACKEND_PORT || "8000";
    return {
        plugins: [react()],
        server: {
            host: "127.0.0.1",
            port: 5173,
            strictPort: true,
            proxy: {
                "/api": {
                    target: "http://127.0.0.1:".concat(backendPort),
                    changeOrigin: true,
                    ws: true,
                    secure: false,
                },
            },
        },
        test: {
            environment: "jsdom",
            globals: true,
            setupFiles: "./src/test/setup.ts",
        },
    };
});
