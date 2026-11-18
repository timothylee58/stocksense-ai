import { Platform } from "react-native";

export const colors = {
  bg: "#F6F4EF",
  panel: "#FFFFFF",
  panelAlt: "#FBFAF6",
  border: "#E6E2D9",
  borderStrong: "#D8D3C8",
  track: "#EFEDE7",
  text: "#17191E",
  muted: "#6E7075",
  faint: "#9C978D",
  accent: "#1F5E46",
  accentSoft: "#E9F1EC",
  danger: "#A33A31",
  dangerSoft: "#F9EBE8",
  warn: "#8A6430",
  warnSoft: "#F7EFE1",
  info: "#4251A8",
  infoSoft: "#ECEEF9",
  chart: "#23252B",
  chartFill: "rgba(35,37,43,0.06)",
};

export const fonts = {
  display: Platform.select({
    ios: "Georgia",
    android: "serif",
    default: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif",
  }),
  sans: Platform.select({
    ios: "System",
    android: "sans-serif",
    default:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
  }),
  mono: Platform.select({
    ios: "Menlo",
    android: "monospace",
    default: "ui-monospace, SFMono-Regular, Menlo, monospace",
  }),
};

export const shadow = Platform.select({
  web: { boxShadow: "0 12px 32px rgba(23, 25, 30, 0.05)" },
  default: {
    shadowColor: "#17191E",
    shadowOpacity: 0.05,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 1,
  },
});

export const space = { xs: 6, sm: 10, md: 16, lg: 24, xl: 32 };
export const radius = { sm: 10, md: 16, lg: 22 };
