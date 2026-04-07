import type { NextConfig } from "next";

const BACKEND_URL =
  process.env.BACKEND_URL || "https://valuescope-production.up.railway.app";

const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  images: {
    remotePatterns: [
      { hostname: "jianshan.co" },
    ],
  },
  experimental: {
    optimizePackageImports: ["recharts", "lucide-react"],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
