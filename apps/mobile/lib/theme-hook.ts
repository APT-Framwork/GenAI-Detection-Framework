/**
 * Reactive theme palette + style builder.
 *
 * The light + dark palettes already live in `theme.ts` (`colors` vs
 * `colors.dark`). This module produces a single flat `palette` object
 * (same key shape both ways) bound to `useUIStore.isDark`, so screens
 * can write:
 *
 *   const c = useColors();
 *   const styles = useThemedStyles(theme => ({
 *     card: { backgroundColor: theme.bgCard, borderRadius: 16 },
 *   }));
 *
 * The dark palette here mirrors the web app's CSS variables
 * (`--strix-bg`, `--strix-bg-card`, `--strix-cyan`, …) so the mobile
 * dark theme looks like the CAVIX web console.
 */

import { useMemo } from "react";
import { StyleSheet } from "react-native";

import { colors as baseColors, shadows as baseShadows } from "./theme";
import { useUIStore } from "../stores/ui-store";

export type ColorPalette = {
  // Surfaces
  bg: string;
  bgCard: string;
  bgSurface: string;
  bgAccent: string;
  bgAccentSoft: string;
  bgAccentLight: string;
  bgOverlay: string;

  // Primary brand
  primary: string;
  primaryDark: string;
  primaryLight: string;

  // Text
  textPrimary: string;
  textBody: string;
  textMuted: string;
  textLight: string;

  // Borders
  border: string;
  borderMedium: string;

  // Severity tokens
  critical: string;
  criticalBg: string;
  warning: string;
  warningBg: string;
  info: string;
  infoBg: string;
  success: string;
  successBg: string;

  // Tab bar
  tabActive: string;
  tabActiveBg: string;
  tabInactive: string;
  tabBar: string;

  // Static
  white: string;
  black: string;
  transparent: string;
};

const LIGHT: ColorPalette = {
  bg:             baseColors.bg,
  bgCard:         baseColors.bgCard,
  bgSurface:      baseColors.bgSurface,
  bgAccent:       baseColors.bgAccent,
  bgAccentSoft:   baseColors.bgAccentSoft,
  bgAccentLight:  baseColors.bgAccentLight,
  bgOverlay:      "rgba(11,14,20,0.45)",

  primary:        baseColors.primary,
  primaryDark:    baseColors.primaryDark,
  primaryLight:   baseColors.primaryLight,

  textPrimary:    baseColors.textPrimary,
  textBody:       baseColors.textBody,
  textMuted:      baseColors.textMuted,
  textLight:      baseColors.textLight,

  border:         baseColors.border,
  borderMedium:   baseColors.borderMedium,

  critical:       baseColors.critical,
  criticalBg:     baseColors.criticalBg,
  warning:        baseColors.warning,
  warningBg:      baseColors.warningBg,
  info:           baseColors.info,
  infoBg:         baseColors.infoBg,
  success:        baseColors.success,
  successBg:      baseColors.successBg,

  tabActive:      baseColors.tabActive,
  tabActiveBg:    baseColors.tabActiveBg,
  tabInactive:    baseColors.tabInactive,
  tabBar:         "rgba(255,255,255,0.92)",

  white:          baseColors.white,
  black:          baseColors.black,
  transparent:    baseColors.transparent,
};

// Dark — anchored to the web app's --strix-* CSS vars in apps/web/app/globals.css.
const DARK: ColorPalette = {
  bg:             baseColors.dark.bg,           // #0b0e14
  bgCard:         baseColors.dark.bgCard,       // #1d2026
  bgSurface:      baseColors.dark.bgSurface,    // #191c22
  bgAccent:       baseColors.dark.primary,      // #00f2ff
  bgAccentSoft:   "rgba(0,242,255,0.08)",
  bgAccentLight:  "rgba(0,242,255,0.16)",
  bgOverlay:      baseColors.dark.bgOverlay,    // rgba(16,19,26,0.8)

  primary:        baseColors.dark.primary,      // #00f2ff
  primaryDark:    "#003a40",
  primaryLight:   "rgba(0,242,255,0.18)",

  textPrimary:    baseColors.dark.textPrimary,  // #e1e2eb
  textBody:       baseColors.dark.textBody,     // #c1c6d6
  textMuted:      baseColors.dark.textDim,      // #849495
  textLight:      baseColors.dark.textDimmer,   // #64748b

  border:         baseColors.dark.border,
  borderMedium:   baseColors.dark.borderAccent,

  critical:       "#ffb4ab",
  criticalBg:     "rgba(255,180,171,0.12)",
  warning:        "#dcb8ff",
  warningBg:      "rgba(220,184,255,0.12)",
  info:           "#00f2ff",
  infoBg:         "rgba(0,242,255,0.08)",
  success:        "#22d3ee",
  successBg:      "rgba(34,211,238,0.12)",

  tabActive:      baseColors.dark.primary,      // cyan glyph
  tabActiveBg:    "rgba(0,242,255,0.16)",
  tabInactive:    baseColors.dark.textDim,
  tabBar:         "rgba(16,19,26,0.92)",

  white:          baseColors.white,
  black:          baseColors.black,
  transparent:    baseColors.transparent,
};

export function useColors(): ColorPalette {
  const isDark = useUIStore((s) => s.isDark);
  return isDark ? DARK : LIGHT;
}

export function useIsDark(): boolean {
  return useUIStore((s) => s.isDark);
}

/**
 * Theme-aware StyleSheet builder. The builder runs on every render but
 * its output is memoized on the palette identity (LIGHT/DARK are
 * frozen module-level objects), so the cost is one shallow object
 * compare per render — cheap.
 */
export function useThemedStyles<T extends StyleSheet.NamedStyles<T>>(
  builder: (theme: ColorPalette) => T,
): T {
  const palette = useColors();
  return useMemo(() => StyleSheet.create(builder(palette)), [palette, builder]);
}

export const shadows = baseShadows;
