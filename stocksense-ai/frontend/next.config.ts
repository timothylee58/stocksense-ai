import type { NextConfig } from "next";

const deploying = Boolean(
  process.env.VERCEL || process.env.BUILD_TARGET === "standalone",
);
if (deploying && !process.env.NEXT_PUBLIC_API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL must be set for a deployment build; refusing to ship a bundle that calls localhost",
  );
}

const nextConfig: NextConfig = {
  // Docker images need a self-contained server; Vercel consumes .next directly,
  // so standalone stays behind BUILD_TARGET.
  output: process.env.BUILD_TARGET === "standalone" ? "standalone" : undefined,
  reactCompiler: true,
  turbopack: process.env.NODE_ENV !== "production" ? {} : undefined,
};

export default nextConfig;
