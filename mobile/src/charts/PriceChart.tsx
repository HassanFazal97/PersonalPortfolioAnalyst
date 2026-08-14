import { useMemo, useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Svg, { Circle, Line, Polygon, Polyline, Text as SvgText } from 'react-native-svg';

import type { Bar } from '@/api/stocks';
import { color, radius, space } from '@/theme/tokens';
import { Txt } from '@/ui/Text';

/**
 * The detail-page price chart, ported from `renderChart` in `app/webapp.py`.
 *
 * Same shape as the web: a polyline over a 4%-padded price range, filled at
 * 8% opacity, coloured by whether the last close beat the first. Two things
 * differ, both because this is a phone:
 *
 * - Geometry is in pixels rather than viewBox units. The web scales one
 *   viewBox to the card width; here the width is measured, which makes the
 *   crosshair a direct touch-x lookup instead of a rect-relative fraction.
 * - The crosshair activates on a long press, not on touch. The chart lives
 *   inside a vertical ScrollView, and a pan that grabs immediately would
 *   swallow the scroll.
 */

const HEIGHT = 200;
const PAD = 12;

export type PriceChartProps = {
  bars: Bar[];
  intraday?: boolean;
  ticker: string;
};

function barLabel(dateStr: string, intraday: boolean): string {
  if (!intraday) return dateStr;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export function PriceChart({ bars, intraday = false, ticker }: PriceChartProps) {
  const [width, setWidth] = useState(0);
  const [cursor, setCursor] = useState<number | null>(null);

  const closes = useMemo(() => bars.map((b) => b.close), [bars]);

  const geometry = useMemo(() => {
    if (closes.length < 2 || width <= 0) return null;
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const span = max - min || 1;
    const lo = min - span * 0.04;
    const hi = max + span * 0.04;
    const x = (i: number) => PAD + (i * (width - 2 * PAD)) / (closes.length - 1);
    const y = (c: number) => HEIGHT - PAD - ((c - lo) * (HEIGHT - 2 * PAD)) / (hi - lo);
    const points = closes.map((c, i) => `${x(i).toFixed(1)},${y(c).toFixed(1)}`).join(' ');
    const up = (closes[closes.length - 1] ?? 0) >= (closes[0] ?? 0);
    return {
      x,
      y,
      points,
      min,
      max,
      stroke: up ? color.gain : color.loss,
      area: `${PAD},${HEIGHT - PAD} ${points} ${width - PAD},${HEIGHT - PAD}`,
    };
  }, [closes, width]);

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  // runOnJS keeps the handlers off the worklet path: a crosshair is not
  // latency-critical, and this avoids a second source of truth for state the
  // SVG already re-renders from.
  const pan = useMemo(
    () =>
      Gesture.Pan()
        .runOnJS(true)
        .activateAfterLongPress(150)
        .onBegin((e) => setCursor(indexAt(e.x)))
        .onUpdate((e) => setCursor(indexAt(e.x)))
        .onFinalize(() => setCursor(null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [width, closes.length],
  );

  function indexAt(px: number): number {
    if (closes.length < 2 || width <= 0) return 0;
    const frac = Math.min(1, Math.max(0, (px - PAD) / (width - 2 * PAD)));
    return Math.round(frac * (closes.length - 1));
  }

  if (closes.length < 2) {
    return (
      <View style={styles.empty} onLayout={onLayout}>
        <Txt variant="bodySm" tone="ink3">
          {intraday
            ? 'No trades yet today; the 1D view fills in once the session opens.'
            : 'Not enough history to chart.'}
        </Txt>
      </View>
    );
  }

  const active = cursor != null && geometry ? cursor : null;
  const activeBar = active != null ? bars[active] : undefined;
  const activeClose = active != null ? closes[active] : undefined;

  return (
    <View onLayout={onLayout}>
      <View style={styles.readout}>
        {activeBar && activeClose != null ? (
          <Txt variant="bodySm" tone="ink" tabular>
            {activeClose.toFixed(2)}
            <Txt variant="bodySm" tone="ink3">
              {'  '}
              {barLabel(activeBar.date, intraday)}
            </Txt>
          </Txt>
        ) : (
          <Txt variant="caption" tone="ink3">
            Touch and hold the chart to read a price.
          </Txt>
        )}
      </View>

      <GestureDetector gesture={pan}>
        <View
          accessible
          accessibilityRole="image"
          accessibilityLabel={`${ticker} prices, ${bars[0]?.date ?? ''} to ${
            bars[bars.length - 1]?.date ?? ''
          }`}
        >
          {geometry && width > 0 ? (
            <Svg width={width} height={HEIGHT}>
              <Polygon points={geometry.area} fill={geometry.stroke} opacity={0.08} />
              <Polyline
                points={geometry.points}
                fill="none"
                stroke={geometry.stroke}
                strokeWidth={1.8}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {active != null && activeClose != null ? (
                <>
                  <Line
                    x1={geometry.x(active)}
                    x2={geometry.x(active)}
                    y1={PAD}
                    y2={HEIGHT - PAD}
                    stroke={color.lineStrong}
                    strokeWidth={1}
                  />
                  <Circle
                    cx={geometry.x(active)}
                    cy={geometry.y(activeClose)}
                    r={3.6}
                    fill={geometry.stroke}
                    stroke={color.surface1}
                    strokeWidth={1.6}
                  />
                </>
              ) : null}
              <SvgText x={PAD} y={12} fill={color.ink3} fontSize={10}>
                {geometry.max.toFixed(2)}
              </SvgText>
              <SvgText x={PAD} y={HEIGHT - 2} fill={color.ink3} fontSize={10}>
                {geometry.min.toFixed(2)}
              </SvgText>
              <SvgText
                x={width - PAD}
                y={HEIGHT - 2}
                textAnchor="end"
                fill={color.ink3}
                fontSize={10}
              >
                {barLabel(bars[bars.length - 1]?.date ?? '', intraday)}
              </SvgText>
            </Svg>
          ) : (
            <View style={{ height: HEIGHT }} />
          )}
        </View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: {
    height: HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surface2,
    borderRadius: radius.m,
  },
  readout: { minHeight: 22, marginBottom: space.s1 },
});
