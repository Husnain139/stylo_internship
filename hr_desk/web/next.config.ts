import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  turbopack: {
    root: process.cwd(),
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
  async rewrites() {
    return {
      fallback: [
        {
          source: "/api/:path*",
          destination: `${process.env.HR_DESK_API_TARGET || "http://127.0.0.1:8000"}/api/:path*`,
        },
      ],
    };
  },
};

export default nextConfig;
