import type { ColorValue } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

/**
 * Tab bar icons, drawn to match `_APP_ICONS` in `app/webapp.py`: a 20-unit
 * box, 1.6 stroke, round joins. Stroke-only so one glyph serves both the
 * active and inactive tint.
 *
 * `color` is a `ColorValue` rather than a string because that is what the
 * navigator hands `tabBarIcon` — it can be a platform colour object, not just
 * a hex literal.
 */
export type IconProps = { color: ColorValue; size?: number };

const S = ({ color, size = 24, children }: IconProps & { children: React.ReactNode }) => (
  <Svg
    width={size}
    height={size}
    viewBox="0 0 20 20"
    fill="none"
    stroke={color}
    strokeWidth={1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </Svg>
);

export const DigestIcon = (p: IconProps) => (
  <S {...p}>
    <Rect x={3} y={3} width={14} height={14} rx={3} />
    <Path d="M6.5 8h7M6.5 11.5h5" />
  </S>
);

export const NewsIcon = (p: IconProps) => (
  <S {...p}>
    <Path d="M13 4H4v12h12V7" />
    <Path d="M13 4h3v3h-3z" />
    <Path d="M6.5 8.5h4M6.5 11.5h6" />
  </S>
);

export const HoldingsIcon = (p: IconProps) => (
  <S {...p}>
    <Circle cx={10} cy={10} r={6.6} />
    <Path d="M10 3.4v6.6l4.7 4.7" />
  </S>
);

export const WatchingIcon = (p: IconProps) => (
  <S {...p}>
    <Path d="m10 3 2.1 4.4 4.7.7-3.4 3.4.8 4.8-4.2-2.3-4.2 2.3.8-4.8L3.2 8.1l4.7-.7z" />
  </S>
);
