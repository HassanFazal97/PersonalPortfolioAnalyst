import { StyleSheet, View } from 'react-native';
import Svg, { G, Path, Text as SvgText } from 'react-native-svg';

import type { Slice } from '@/dashboard/portfolio';
import { color, radius, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

/**
 * The allocation donut, ported from `renderHoldingsPie` in `app/webapp.py`.
 *
 * Same geometry (r 80 / 48 in a 200 box, starting at twelve o'clock and going
 * clockwise) and the same 2.5-unit stroke in the card's own surface colour,
 * which cuts the visible gap that keeps touching wedges reading as separate
 * slices rather than one flat ring.
 */

const R = 80;
const RI = 48;
const C = 100;

function point(r: number, fraction: number): string {
  const angle = fraction * 2 * Math.PI - Math.PI / 2;
  return `${(C + r * Math.cos(angle)).toFixed(2)} ${(C + r * Math.sin(angle)).toFixed(2)}`;
}

function wedge(from: number, to: number): string {
  const large = to - from > 0.5 ? 1 : 0;
  return [
    `M ${point(R, from)}`,
    `A ${R} ${R} 0 ${large} 1 ${point(R, to)}`,
    `L ${point(RI, to)}`,
    `A ${RI} ${RI} 0 ${large} 0 ${point(RI, from)}`,
    'Z',
  ].join(' ');
}

export function Donut({ slices, count }: { slices: Slice[]; count: number }) {
  if (!slices.length) return null;

  let acc = 0;
  const paths = slices.map((slice) => {
    const from = acc;
    acc += slice.fraction;
    return { d: wedge(from, acc), color: slice.color, ticker: slice.ticker };
  });

  return (
    <View style={styles.row}>
      <Svg width={124} height={124} viewBox="0 0 200 200" accessibilityRole="image">
        <G>
          {paths.map((p) => (
            <Path
              key={p.ticker}
              d={p.d}
              fill={p.color}
              stroke={color.surface1}
              strokeWidth={2.5}
              strokeLinejoin="round"
            />
          ))}
        </G>
        <SvgText x={100} y={97} textAnchor="middle" fill={color.ink} fontSize={30} fontWeight="700">
          {String(count)}
        </SvgText>
        <SvgText
          x={100}
          y={118}
          textAnchor="middle"
          fill={color.ink3}
          fontSize={10.5}
          fontWeight="600"
          letterSpacing={0.5}
        >
          {count === 1 ? 'HOLDING' : 'HOLDINGS'}
        </SvgText>
      </Svg>

      <View style={styles.legend}>
        {slices.map((slice) => (
          <View key={slice.ticker} style={styles.legendRow}>
            <View style={[styles.swatch, { backgroundColor: slice.color }]}>
              {slice.other ? null : (
                <Txt variant="label" tone="inverse">
                  {slice.ticker.slice(0, 1)}
                </Txt>
              )}
            </View>
            <Txt variant="caption" tone={slice.other ? 'ink3' : 'ink'} style={styles.name}>
              {slice.ticker}
            </Txt>
            <Txt variant="caption" tone="ink3" tabular>
              {(slice.fraction * 100).toFixed(1)}%
            </Txt>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s3 },
  legend: { flex: 1, gap: 3 },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: space.s2 },
  swatch: {
    width: 16,
    height: 16,
    borderRadius: radius.s - 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: { flex: 1, fontWeight: '600' },
});
