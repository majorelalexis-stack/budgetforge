import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8011";
    return [
      { source: "/api/:path*",   destination: `${base}/api/:path*` },
      { source: "/health",       destination: `${base}/health` },
      { source: "/proxy/:path*", destination: `${base}/proxy/:path*` },
    ];
  },
};

export default nextConfig;
