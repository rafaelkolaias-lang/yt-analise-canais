"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TimeseriesPoint } from "@/lib/api";

type Kind = "line" | "bar";

type Props = {
  title: string;
  data: TimeseriesPoint[];
  kind?: Kind;
  color?: string;
  formatValue?: (v: number) => string;
};

function defaultFormat(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return String(Math.round(v));
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ChannelChart({
  title,
  data,
  kind = "line",
  color = "#4f8cff",
  formatValue = defaultFormat,
}: Props) {
  const clean = data
    .filter((p) => p.value !== null && p.captured_at)
    .map((p) => ({
      captured_at: p.captured_at!,
      value: p.value as number,
      label: formatDate(p.captured_at),
    }));

  if (clean.length === 0) {
    return (
      <div className="analytics-chart-box">
        <div className="analytics-chart-title">{title}</div>
        <div className="analytics-empty-chart">coletando dados…</div>
      </div>
    );
  }

  const Chart = kind === "bar" ? BarChart : LineChart;
  return (
    <div className="analytics-chart-box">
      <div className="analytics-chart-title">{title}</div>
      <ResponsiveContainer width="100%" height={150}>
        <Chart data={clean} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1f2a4a" strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            stroke="#8b93ad"
            fontSize={10}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            stroke="#8b93ad"
            fontSize={10}
            tickFormatter={(v: number) => formatValue(v)}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: "#111833",
              border: "1px solid #1f2a4a",
              borderRadius: 6,
              fontSize: 12,
            }}
            labelStyle={{ color: "#8b93ad" }}
            formatter={(v: number) => [formatValue(v), title]}
          />
          {kind === "bar" ? (
            <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} />
          ) : (
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={{ r: 2 }}
              activeDot={{ r: 4 }}
            />
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}
