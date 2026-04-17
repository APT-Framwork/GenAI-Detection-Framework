// STRIX Design System — extracted from Figma light-mode frames
export const colors = {
  // Backgrounds
  bg: "#e7faff",
  bgCard: "#ffffff",
  bgSurface: "#d6f6ff",
  bgAccent: "#87edf6",
  bgAccentAlt: "#9ae9fc",
  bgAccentSoft: "#baf1ff",
  bgAccentLight: "#a6eeff",

  // Primary
  primary: "#00666d",
  primaryDark: "#00343d",
  primaryLight: "#cffbff",

  // Text
  textPrimary: "#00343d",
  textBody: "#2b636f",
  textMuted: "#497f8b",
  textLight: "#80b6c3",

  // Borders
  border: "rgba(128,182,195,0.15)",
  borderMedium: "rgba(128,182,195,0.3)",

  // Severity
  critical: "#b31b25",
  criticalBg: "rgba(179,27,37,0.08)",
  warning: "#005ea0",
  warningBg: "rgba(0,94,160,0.08)",
  info: "#80b6c3",
  infoBg: "rgba(128,182,195,0.08)",
  success: "#00666d",
  successBg: "rgba(0,102,109,0.08)",

  // Tab bar
  tabActive: "#00343d",
  tabActiveBg: "#87edf6",
  tabInactive: "#497f8b",

  // Dark mode (from dark frames 9-xxxx)
  dark: {
    bg: "#0b0e14",
    bgCard: "#1d2026",
    bgSurface: "#191c22",
    bgOverlay: "rgba(16,19,26,0.8)",
    primary: "#00f2ff",
    primaryAlt: "#22d3ee",
    accent: "#dcb8ff",
    textPrimary: "#e1e2eb",
    textBody: "#c1c6d6",
    textMuted: "#b9cacb",
    textDim: "#849495",
    textDimmer: "#64748b",
    border: "rgba(58,73,75,0.2)",
    borderAccent: "rgba(0,242,255,0.1)",
    criticalText: "#ffb4ab",
    warningText: "#ead2ff",
    infoText: "#00f2ff",
  },

  // Common
  white: "#ffffff",
  black: "#000000",
  transparent: "transparent",
} as const;

export const typography = {
  family: {
    heading: "SpaceGrotesk-Bold",
    headingMedium: "SpaceGrotesk-Medium",
    headingRegular: "SpaceGrotesk-Regular",
    body: "Inter-Regular",
    bodyMedium: "Inter-Medium",
    bodySemiBold: "Inter-SemiBold",
    mono: "Liberation Mono",
  },
  size: {
    xs: 10,
    sm: 12,
    md: 14,
    lg: 16,
    xl: 18,
    "2xl": 20,
    "3xl": 24,
    "4xl": 30,
    "5xl": 36,
    "6xl": 48,
  },
  lineHeight: {
    xs: 15,
    sm: 16,
    md: 20,
    lg: 24,
    xl: 28,
    "2xl": 28,
    "3xl": 32,
    "4xl": 36,
    "5xl": 40,
    "6xl": 48,
  },
  tracking: {
    tighter: -2.4,
    tight: -0.9,
    normal: 0,
    wide: 0.5,
    wider: 1,
    widest: 2.4,
    ultra: 3.6,
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  "2xl": 48,
  "3xl": 64,
  "4xl": 96,
} as const;

export const radius = {
  sm: 2,
  md: 16,
  lg: 32,
  xl: 48,
  full: 9999,
} as const;

export const shadows = {
  card: {
    shadowColor: "#00343d",
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.06,
    shadowRadius: 32,
    elevation: 4,
  },
  cardUp: {
    shadowColor: "#00343d",
    shadowOffset: { width: 0, height: -12 },
    shadowOpacity: 0.06,
    shadowRadius: 32,
    elevation: 4,
  },
  button: {
    shadowColor: "#00666d",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.2,
    shadowRadius: 15,
    elevation: 6,
  },
  fab: {
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.1,
    shadowRadius: 15,
    elevation: 8,
  },
} as const;
