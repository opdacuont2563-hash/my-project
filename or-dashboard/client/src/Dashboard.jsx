import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  Legend,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell
} from "recharts";
import { api } from "./api";

const weekdayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const chartPalette = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#8dd1e1", "#a4de6c"];

function minutesToText(min = 0) {
  const value = Number(min) || 0;
  const hours = Math.floor(value / 60);
  const minutes = Math.round(value % 60);
  if (!hours) {
    return `${minutes} min`;
  }
  return `${hours}h ${minutes}m`;
}

export default function Dashboard() {
  const [range, setRange] = useState({ from: "", to: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const params = useMemo(() => ({
    from: range.from || undefined,
    to: range.to || undefined
  }), [range]);

  const [kpi, setKpi] = useState(null);
  const [trend, setTrend] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [firstCut, setFirstCut] = useState([]);
  const [operations, setOperations] = useState([]);
  const [postpone, setPostpone] = useState([]);
  const [heatmap, setHeatmap] = useState([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [kpiData, trendData, roomData, firstCutData, opsData, postponeData, heatmapData] = await Promise.all([
          api.kpi(params),
          api.trend({ ...params, granularity: "day" }),
          api.rooms(params),
          api.firstcut(params),
          api.topops(params),
          api.postpone(params),
          api.heatmap(params)
        ]);
        if (!cancelled) {
          setKpi(kpiData);
          setTrend(trendData);
          setRooms(roomData);
          setFirstCut(firstCutData);
          setOperations(opsData);
          setPostpone(postponeData);
          setHeatmap(heatmapData);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load dashboard data");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [params]);

  return (
    <div style={{ padding: 16, display: "grid", gap: 16 }}>
      <header>
        <h1 style={{ marginBottom: 8 }}>OR Dashboard</h1>
        <p style={{ margin: 0, color: "#475569" }}>
          ตรวจสอบภาระงานห้องผ่าตัด (Operating Room) แบบเรียลไทม์ พร้อมตัวชี้วัดสำคัญ
        </p>
      </header>

      <FilterBar range={range} onChange={setRange} loading={loading} />
      {error && <ErrorBanner message={error} />}

      {kpi && (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <KpiCard title="จำนวนเคส" value={kpi.cases.toLocaleString()} />
          <KpiCard title="เวลาผ่าตัดรวม" value={minutesToText(kpi.case_min)} />
          <KpiCard title="เวลาพร้อมใช้งาน" value={minutesToText(kpi.avail_min)} />
          <KpiCard title="Utilization" value={`${kpi.utilization_pct.toFixed(1)}%`} />
          <KpiCard title="เวลาต่อเคส (เฉลี่ย)" value={`${kpi.avg_case_min.toFixed(1)} นาที`} />
          <KpiCard title="เลื่อน / ยกเลิก" value={`${kpi.postponed_cases} / ${kpi.cancelled_cases}`} />
        </div>
      )}

      <ChartCard title="ปริมาณเคส & Utilization (รายวัน)">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="bucket" />
            <YAxis yAxisId="left" />
            <YAxis yAxisId="right" orientation="right" />
            <Tooltip />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="cases" name="จำนวนเคส" stroke={chartPalette[0]} />
            <Line yAxisId="right" type="monotone" dataKey="utilization_pct" name="Util (%)" stroke={chartPalette[1]} />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="ห้องผ่าตัดที่ใช้งานมากที่สุด">
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={rooms}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="room_id" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="utilization_pct" name="Util (%)" fill={chartPalette[1]} />
            <Bar dataKey="avg_case_min" name="เวลาเฉลี่ยต่อเคส (นาที)" fill={chartPalette[0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="ศัลยแพทย์ที่เริ่มเคสแรกเร็วที่สุด (เฉลี่ย)">
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={firstCut}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="doctor" />
            <YAxis label={{ value: "นาทีหลัง 00:00", angle: -90, position: "insideLeft" }} />
            <Tooltip formatter={(value) => minutesToText(Number(value))} />
            <Legend />
            <Bar dataKey="avg_first_minutes" name="เวลาตัดครั้งแรก (นาที)" fill={chartPalette[2]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="หัตถการยอดนิยม">
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={operations}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="operation" interval={0} angle={-25} textAnchor="end" height={140} />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="cases" name="จำนวนเคส" fill={chartPalette[0]} />
            <Bar dataKey="avg_min" name="เวลาเฉลี่ย (นาที)" fill={chartPalette[1]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="สาเหตุการเลื่อนผ่าตัด">
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie dataKey="cases" data={postpone} nameKey="reason" outerRadius={120} label>
              {postpone.map((_, index) => (
                <Cell key={index} fill={chartPalette[index % chartPalette.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="Heatmap ชั่วโมง x วัน">
        <Heatmap data={heatmap} />
      </ChartCard>
    </div>
  );
}

function FilterBar({ range, onChange, loading }) {
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
      <label style={{ display: "flex", flexDirection: "column", fontSize: 13 }}>
        จากวันที่
        <input
          type="date"
          value={range.from}
          onChange={(event) => onChange((prev) => ({ ...prev, from: event.target.value }))}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column", fontSize: 13 }}>
        ถึงวันที่
        <input
          type="date"
          value={range.to}
          onChange={(event) => onChange((prev) => ({ ...prev, to: event.target.value }))}
        />
      </label>
      {loading && <span style={{ color: "#2563eb", fontWeight: 600 }}>กำลังโหลด...</span>}
    </div>
  );
}

function ErrorBanner({ message }) {
  return (
    <div style={{ borderRadius: 8, padding: 12, background: "#fee2e2", color: "#b91c1c" }}>
      {message}
    </div>
  );
}

function KpiCard({ title, value }) {
  return (
    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function ChartCard({ title, children }) {
  return (
    <section style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 16 }}>
      <h2 style={{ margin: "0 0 12px", fontSize: 18 }}>{title}</h2>
      {children}
    </section>
  );
}

function Heatmap({ data }) {
  const matrix = useMemo(() => {
    const grid = Array.from({ length: 7 }, () => Array(24).fill(0));
    data.forEach((item) => {
      const dowIndex = Number(item.dow) - 1;
      const hour = Number(item.hour);
      if (dowIndex >= 0 && dowIndex < 7 && hour >= 0 && hour < 24) {
        grid[dowIndex][hour] = Number(item.cases || 0);
      }
    });
    return grid;
  }, [data]);

  const max = Math.max(1, ...matrix.flat());

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>วัน</th>
            {Array.from({ length: 24 }, (_, hour) => (
              <th key={hour} style={{ padding: 4, fontSize: 11 }}>{hour}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, rowIndex) => (
            <tr key={rowIndex}>
              <td style={{ padding: "4px 8px", fontSize: 12 }}>{weekdayLabels[rowIndex]}</td>
              {row.map((value, hour) => {
                const alpha = value / max;
                const background = `rgba(30, 144, 255, ${alpha.toFixed(2)})`;
                return (
                  <td
                    key={`${rowIndex}-${hour}`}
                    title={`${weekdayLabels[rowIndex]} ${hour}:00 = ${value}`}
                    style={{
                      width: 18,
                      height: 18,
                      background,
                      border: "1px solid #ffffff"
                    }}
                  />
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
