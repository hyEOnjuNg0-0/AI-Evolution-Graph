import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy /api/* requests to the FastAPI backend so the browser never
  // needs direct access to port 8000 (no CORS configuration required).
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
