import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Animated,
  Easing,
  Platform,
  useWindowDimensions,
  type LayoutChangeEvent,
  type StyleProp,
  type ViewStyle,
} from "react-native";

interface Props {
  children: ReactNode;
  index?: number;
  scrollY?: Animated.Value;
  distance?: number;
  style?: StyleProp<ViewStyle>;
}

export function Reveal({ children, index = 0, scrollY, distance = 18, style }: Props) {
  const { height } = useWindowDimensions();
  const [offsetY, setOffsetY] = useState<number | null>(null);
  const mount = useRef(new Animated.Value(scrollY ? 1 : 0)).current;

  useEffect(() => {
    if (scrollY) return;
    Animated.timing(mount, {
      toValue: 1,
      duration: 520,
      delay: Math.min(index, 8) * 70,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: Platform.OS !== "web",
    }).start();
  }, [index, mount, scrollY]);

  const onLayout = (event: LayoutChangeEvent) => setOffsetY(event.nativeEvent.layout.y);

  let opacity: Animated.Value | Animated.AnimatedInterpolation<number> = mount;
  let translateY: Animated.Value | Animated.AnimatedInterpolation<number> = mount.interpolate({
    inputRange: [0, 1],
    outputRange: [distance, 0],
  });

  if (scrollY) {
    const y = offsetY ?? height * 4;
    const start = y - height + 96;
    const end = start + 150;
    const range = { inputRange: [start, end], extrapolate: "clamp" as const };
    opacity = scrollY.interpolate({ ...range, outputRange: [0, 1] });
    translateY = scrollY.interpolate({ ...range, outputRange: [distance, 0] });
  }

  return (
    <Animated.View onLayout={onLayout} style={[style, { opacity, transform: [{ translateY }] }]}>
      {children}
    </Animated.View>
  );
}
