"use client";

import React from "react";

interface SkeletonProps {
  className?: string;
  /** Width override (e.g. "120px", "60%"). Defaults to 100%. */
  width?: string | number;
  /** Height override (e.g. "16px"). Defaults to "1em". */
  height?: string | number;
  /** Corner radius. Defaults to "4px". */
  radius?: string | number;
}

/**
 * Animated loading placeholder. Drop-in replacement for content that hasn't
 * loaded yet.  Uses CSS animation rather than Tailwind animate-pulse so it
 * works independently of the Tailwind config.
 */
export function Skeleton({ className = "", width, height, radius }: SkeletonProps) {
  return (
    <span
      className={className}
      style={{
        display: "inline-block",
        width: width ?? "100%",
        height: height ?? "1em",
        borderRadius: radius ?? 4,
        background: "linear-gradient(90deg, rgba(23,25,30,0.05) 25%, rgba(23,25,30,0.10) 50%, rgba(23,25,30,0.05) 75%)",
        backgroundSize: "200% 100%",
        animation: "skeleton-shimmer 1.4s ease-in-out infinite",
        verticalAlign: "middle",
      }}
    >
      <style>{`
        @keyframes skeleton-shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </span>
  );
}

/** Block-level skeleton row — convenience wrapper for text lines. */
export function SkeletonLine({ width = "100%", className = "" }: { width?: string | number; className?: string }) {
  return <Skeleton width={width} height="0.875rem" radius={3} className={className} />;
}

export default Skeleton;
