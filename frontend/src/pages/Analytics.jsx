/* Avatar Studio — Analitika ekrani (latency, hajm, kesh, top so'rovlar).
   Yengil inline SVG/CSS grafiklar, tashqi kutubxonasiz. */
import React from "react";
import { I } from "../lib/icons";
import { API } from "../api/client";
import { Card, Badge, Btn, Portrait } from "../components/ui/index.jsx";
import { Topbar } from "../components/AdminShell.jsx";
import { ANALYTICS } from "../data/constants";

export function Analytics({ avatars }) {
  const [A, setA] = React.useState(ANALYTICS);
  React.useEffect(() => { API.analytics().then(setA).catch((e) => console.error(e)); }, []);
  const daily = A.daily && A.daily.length ? A.daily : [];
  const maxS = daily.length ? Math.max(...daily.map((d) => d.sessions), 1) : 1;
  const totalLat = A.latencyBreakdown.reduce((s, x) => s + x.value, 0);
  const maxAvSessions = Math.max(...avatars.map((a) => a.sessions || 0), 1);

  return (
    <div className="pg as-scroll">
      <Topbar title="Analitika" sub="So‘nggi 14 kun · barcha avatarlar"
        actions={<Btn kind="ghost" icon="copy">Hisobot eksport</Btn>} />

      <div className="pg-body">
        <div className="an-kpis">
          {[
            { k: "Jami sessiyalar", v: A.totals.sessions.toLocaleString("ru"), d: "+12%", up: true },
            { k: "O‘rtacha latency", v: A.totals.avgLatency + "s", d: "−0.3s", up: true },
            { k: "Cache darajasi", v: A.totals.cacheRate + "%", d: "+5%", up: true },
            { k: "CSAT", v: A.totals.csat.toFixed(1) + " / 5", d: "+0.2", up: true },
            { k: "Uptime", v: A.totals.uptime + "%", d: "30 kun", up: true },
          ].map((k) => (
            <Card key={k.k} className="an-kpi">
              <div className="as-label">{k.k}</div>
              <div className="an-kpi-v">{k.v}</div>
              <div className={"an-kpi-d" + (k.up ? " up" : "")}>{k.d}</div>
            </Card>
          ))}
        </div>

        <div className="an-grid">
          {/* volume chart */}
          <Card className="an-chart">
            <div className="an-chart-head">
              <div>
                <div className="an-chart-title">Kunlik sessiyalar</div>
                <div className="an-chart-sub">So‘nggi 14 kun</div>
              </div>
              <Badge color="var(--brass)">Sessiya</Badge>
            </div>
            <div className="an-bars">
              {daily.map((d) => (
                <div key={d.d} className="an-bar-col" title={`${d.d}: ${d.sessions}`}>
                  <div className="an-bar" style={{ height: (d.sessions / maxS * 100) + "%" }} />
                  <div className="an-bar-x">{d.d}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* latency breakdown */}
          <Card className="an-chart">
            <div className="an-chart-head">
              <div>
                <div className="an-chart-title">Latency tarkibi</div>
                <div className="an-chart-sub">O‘rtacha {totalLat.toFixed(1)}s / javob</div>
              </div>
            </div>
            <div className="an-stack">
              {A.latencyBreakdown.map((x) => (
                <div key={x.stage} className="an-stack-seg" style={{ flex: x.value, background: x.color }} />
              ))}
            </div>
            <div className="an-legend">
              {A.latencyBreakdown.map((x) => (
                <div key={x.stage} className="an-legend-row">
                  <span className="an-legend-dot" style={{ background: x.color }} />
                  <span className="an-legend-k">{x.stage}</span>
                  <span className="an-legend-v">{x.value.toFixed(1)}s</span>
                </div>
              ))}
            </div>
            <div className="an-ring-note">
              <I.bolt size={13} /> Cache hit javoblari ~0s — {A.totals.cacheRate}% so‘rovlar keshdan.
            </div>
          </Card>
        </div>

        <div className="an-grid">
          {/* top queries */}
          <Card className="an-table">
            <div className="an-chart-head">
              <div className="an-chart-title">Eng ko‘p so‘ralganlar</div>
            </div>
            <div className="an-table-rows">
              {A.topQueries.map((q, i) => (
                <div key={i} className="an-tr">
                  <span className="an-tr-num">{String(i+1).padStart(2,"0")}</span>
                  <span className="an-tr-q">{q.q}</span>
                  {q.cached && <span className="an-tr-cache"><I.bolt size={11} />kesh</span>}
                  <span className="an-tr-n">{q.n.toLocaleString("ru")}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* per-avatar */}
          <Card className="an-table">
            <div className="an-chart-head">
              <div className="an-chart-title">Avatarlar bo‘yicha</div>
            </div>
            <div className="an-table-rows">
              {avatars.filter((a) => a.sessions > 0).map((a) => (
                <div key={a.id} className="an-av-row">
                  <Portrait avatar={a} size={34} radius="8px" />
                  <div className="an-av-meta">
                    <div className="an-av-name">{a.name}</div>
                    <div className="an-av-brand">{a.brandShort}</div>
                  </div>
                  <div className="an-av-bar-wrap">
                    <div className="an-av-bar" style={{ width: (a.sessions / maxAvSessions * 100) + "%", background: a.accent }} />
                  </div>
                  <div className="an-av-n">{a.sessions.toLocaleString("ru")}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
