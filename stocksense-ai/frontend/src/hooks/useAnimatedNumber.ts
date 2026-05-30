"use client";
import { useEffect, useRef } from "react";
import { useMotionValue, useSpring, useTransform, MotionValue } from "framer-motion";

export function useAnimatedNumber(target: number, decimals = 2): MotionValue<string> {
  const motionVal = useMotionValue(target);
  const spring = useSpring(motionVal, { stiffness: 200, damping: 25 });
  const display = useTransform(spring, (v) => v.toFixed(decimals));

  useEffect(() => {
    motionVal.set(target);
  }, [target, motionVal]);

  return display;
}
