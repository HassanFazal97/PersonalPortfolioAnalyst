import React from "react";
import { interpolate } from "remotion";
import { panelStyle } from "./components";
import { C, ease, rise } from "./theme";

/**
 * Faithful recreation of the real /app/dashboard from app/webapp.py:
 * topbar (Dashboard + account email), Holdings table (Ticker/Qty/Value/
 * Day/Total, uppercase headers, tabular numerals), General news feed with
 * severity-tagged items, and the Delivery card. Values sum to $48,214.
 */

export const HOLDINGS = [
  { t: "VFV", qty: 159, val: "$22,451", day: "+0.8%", tot: "+21.4%", dGain: true, tGain: true, hit: false },
  { t: "NVDA", qty: 36, val: "$5,832", day: "+2.1%", tot: "+64.2%", dGain: true, tGain: true, hit: false },
  { t: "ENB", qty: 210, val: "$11,378", day: "−1.2%", tot: "+8.9%", dGain: false, tGain: true, hit: true },
  { t: "SU", qty: 95, val: "$4,982", day: "−2.4%", tot: "+12.1%", dGain: false, tGain: true, hit: true },
  { t: "T.TO", qty: 160, val: "$3,571", day: "+0.3%", tot: "−2.2%", dGain: true, tGain: false, hit: false },
] as const;

const cardStyle: React.CSSProperties = {
  background: C.surface1,
  border: `1px solid ${C.line}`,
  borderRadius: 18,
  padding: "22px 26px",
};

const h3Style: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  gap: 16,
  fontSize: 19,
  fontWeight: 650,
  color: C.ink,
};

const NewsItem: React.FC<{
  head: string;
  body: string;
  meta: React.ReactNode;
  last?: boolean;
  style?: React.CSSProperties;
}> = ({ head, body, meta, last, style }) => (
  <div
    style={{
      padding: "13px 0",
      borderBottom: last ? "none" : `1px solid ${C.line}`,
      ...style,
    }}
  >
    <div style={{ fontWeight: 650, fontSize: 16.5, color: C.ink, lineHeight: 1.35 }}>{head}</div>
    <div style={{ color: C.ink2, fontSize: 15, marginTop: 5, lineHeight: 1.5 }}>{body}</div>
    <div style={{ color: C.ink3, fontSize: 13, marginTop: 4 }}>{meta}</div>
  </div>
);

export const AppDashboard: React.FC<{
  frame: number;
  /** rows stagger in starting here (pass a negative number to show instantly) */
  rowsAt?: number;
  /** totals tag ticks up starting here */
  tickAt?: number;
  /** ENB + SU rows tint amber starting here */
  highlightAt?: number;
  /** macro alert item appears at top of the news feed starting here */
  alertAt?: number;
}> = ({ frame, rowsAt = -999, tickAt = -999, highlightAt = 99999, alertAt = 99999 }) => {
  const total = Math.round(
    interpolate(ease(frame, tickAt, 40), [0, 1], [47734, 48214]),
  ).toLocaleString("en-CA");
  const alertT = ease(frame, alertAt, 20);
  let hitIndex = 0;
  return (
    <div style={{ width: 1200, fontSize: 16 }}>
      {/* topbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 18,
        }}
      >
        <span style={{ fontSize: 24, fontWeight: 700, color: C.ink, letterSpacing: "-0.015em" }}>
          Dashboard
        </span>
        <span style={{ color: C.ink3, fontSize: 15 }}>sam.k@gmail.com</span>
      </div>

      {/* holdings card */}
      <div style={cardStyle}>
        <div style={h3Style}>
          Holdings
          <span style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
            <span style={{ color: C.ink3, fontSize: 13.5, fontWeight: 500 }}>Updated 7:44 AM</span>
            <span style={{ color: C.accentText, fontSize: 14.5, fontWeight: 500 }}>Refresh</span>
            <span
              style={{
                color: C.ink3,
                fontSize: 15,
                fontWeight: 600,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              ${total} · <span style={{ color: C.gain }}>+1.2% today</span>
            </span>
          </span>
        </div>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            marginTop: 12,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          <thead>
            <tr>
              {["Ticker", "Qty", "Value", "Day", "Total"].map((h, i) => (
                <th
                  key={h}
                  style={{
                    textAlign: i === 0 ? "left" : "right",
                    color: C.ink3,
                    fontWeight: 600,
                    fontSize: 12,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    padding: "7px 10px",
                    borderBottom: `1px solid #3b3744`,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {HOLDINGS.map((r, i) => {
              const hl = r.hit ? ease(frame, highlightAt + hitIndex++ * 10, 18) : 0;
              return (
                <tr key={r.t} style={rise(frame, rowsAt + i * 4, 12, 6)}>
                  {[
                    <span style={{ fontWeight: 700, color: C.ink }}>{r.t}</span>,
                    r.qty,
                    r.val,
                    <span style={{ color: r.dGain ? C.gain : C.loss }}>{r.day}</span>,
                    <span style={{ color: r.tGain ? C.gain : C.loss }}>{r.tot}</span>,
                  ].map((cell, j) => (
                    <td
                      key={j}
                      style={{
                        padding: "10px 10px",
                        borderBottom: i < HOLDINGS.length - 1 ? `1px solid ${C.line}` : "none",
                        textAlign: j === 0 ? "left" : "right",
                        color: C.ink2,
                        fontSize: 15.5,
                        background: `rgba(222,184,102,${hl * 0.09})`,
                      }}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* news + delivery */}
      <div style={{ display: "grid", gridTemplateColumns: "1.35fr 1fr", gap: 16, marginTop: 16 }}>
        <div style={cardStyle}>
          <div style={h3Style}>General news</div>
          <div style={{ marginTop: 4 }}>
            {frame >= alertAt ? (
              <NewsItem
                style={{
                  opacity: alertT,
                  transform: `translateY(${(1 - alertT) * -10}px)`,
                }}
                head="OPEC+ signals higher August output"
                body="Crude down 3%. Touches ENB and SU in your portfolio."
                meta={
                  <>
                    alert · <span style={{ color: C.warn, fontWeight: 600 }}>medium</span> · energy
                    · just now
                  </>
                }
              />
            ) : null}
            <NewsItem
              head="Morning digest — Jul 6"
              body="Quiet overnight session. NVDA up premarket ahead of Wednesday earnings; BoC rate decision lands Thursday."
              meta="digest · 7:45 AM"
            />
            <NewsItem
              head="Bank of Canada decision preview"
              body="Markets price no change; statement language is the watch item for rate-sensitive names."
              meta={
                <>
                  general · <span style={{ color: C.ink3, fontWeight: 600 }}>low</span> · monetary ·
                  yesterday
                </>
              }
              last
            />
          </div>
        </div>
        <div style={cardStyle}>
          <div style={h3Style}>
            Delivery
            <span style={{ color: C.accentText, fontSize: 14.5, fontWeight: 500 }}>Change</span>
          </div>
          <div style={{ marginTop: 14, fontSize: 15.5, color: C.ink2, lineHeight: 1.7 }}>
            <div>
              SMS to +1 ••• 4821{" "}
              <span style={{ color: C.gain, fontSize: 13.5, fontWeight: 600 }}>Verified</span>
            </div>
            <div style={{ color: C.ink3 }}>Weekdays at 7:45 AM · America/Toronto</div>
          </div>
          <div
            style={{
              marginTop: 16,
              paddingTop: 14,
              borderTop: `1px solid ${C.line}`,
              color: C.ink3,
              fontSize: 13.5,
            }}
          >
            Read-only connection · Wealthsimple via SnapTrade
          </div>
        </div>
      </div>
    </div>
  );
};

/** macOS-style popup notification, slides in from the right. */
export const NotificationPopup: React.FC<{
  frame: number;
  at: number;
  title: string;
  body: string;
}> = ({ frame, at, title, body }) => {
  const t = ease(frame, at, 24);
  return (
    <div
      style={{
        ...panelStyle,
        width: 440,
        padding: "16px 20px",
        borderRadius: 16,
        background: "#17141d",
        opacity: t,
        transform: `translateX(${(1 - t) * 60}px)`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontSize: 13.5,
          fontWeight: 600,
          color: C.ink3,
          marginBottom: 7,
        }}
      >
        <span
          style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: C.accent,
            color: "#fff",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            fontWeight: 800,
          }}
        >
          C
        </span>
        CIRVIA
        <span style={{ marginLeft: "auto", fontWeight: 500 }}>now</span>
      </div>
      <div style={{ fontSize: 17, fontWeight: 700, color: C.ink }}>{title}</div>
      <div style={{ fontSize: 15.5, color: C.ink2, marginTop: 3, lineHeight: 1.45 }}>{body}</div>
    </div>
  );
};
