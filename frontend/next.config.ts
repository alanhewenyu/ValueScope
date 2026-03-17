import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { hostname: "jianshan.co" },
    ],
  },
};

export default nextConfig;
