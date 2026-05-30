import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
  turbopack: process.env.NODE_ENV === "production" ? false : true,
};

export default nextConfig;
