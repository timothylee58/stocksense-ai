import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
  turbopack: process.env.NODE_ENV !== "production" ? {} : undefined,
};

export default nextConfig;
