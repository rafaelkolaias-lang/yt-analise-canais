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

// Filtro de PERÍODO: 'all' = histórico inteiro; 7d/30d = só os snapshots dos
// últimos N dias (contados a partir do ponto mais recente da série — assim o
// gráfico não fica vazio se o sync estiver atrasado). Não agrega nada: os
// pontos continuam sendo os snapshots crus, com o teto de MAX_POINTS valendo.
export type ChartPeriod = "all" | "7d" | "30d";

// Critério do downsample (teto de pontos): para métricas cumulativas (views,
// inscritos) usamos o último valor do grupo; para derivadas (VPD, uploads/sem)
// usamos a média.
export type ChartAggregation = "last" | "avg";

// Teto de pontos por gráfico. Como o sync roda várias vezes ao dia, a série
// "Todos" pode ter centenas de pontos colados e poluir o gráfico. Acima deste
// limite, reamostramos pra no máximo MAX_POINTS preservando o formato da curva
// e sempre o último ponto.
const MAX_POINTS = 100;

type Props = {
  title: string;
  data: TimeseriesPoint[];
  kind?: Kind;
  color?: string;
  formatValue?: (v: number) => string;
  period?: ChartPeriod;
  aggregation?: ChartAggregation;
  // Corta outliers extremos do eixo Y (picos falsos de snapshot defeituoso):
  // a escala passa a cobrir só a faixa "normal" dos dados e o pico é desenhado
  // cortado na borda, em vez de achatar o gráfico inteiro. O tooltip continua
  // mostrando o valor real do ponto.
  clampOutliers?: boolean;
};

function defaultFormat(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return String(Math.round(v));
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type CleanPoint = { captured_at: string; value: number };

// Mantém só os pontos dos últimos N dias, contados a partir do ponto mais
// recente da série (não do "agora" do cliente — evita gráfico vazio quando o
// sync está atrasado).
function filterPeriod(points: CleanPoint[], days: number): CleanPoint[] {
  if (points.length === 0) return points;
  const sorted = [...points].sort(
    (a, b) => new Date(a.captured_at).getTime() - new Date(b.captured_at).getTime()
  );
  const anchor = new Date(sorted[sorted.length - 1].captured_at).getTime();
  const cutoff = anchor - days * 24 * 60 * 60 * 1000;
  return sorted.filter((p) => new Date(p.captured_at).getTime() >= cutoff);
}

// Domínio "robusto" do eixo Y: cerca de Tukey (quartis ± 3×IQR). Devolve null
// quando não há outlier — aí o eixo fica no automático do recharts. Com menos
// de 8 pontos não dá pra estimar quartil com confiança, então não corta nada.
function robustDomain(values: number[]): [number, number] | null {
  if (values.length < 8) return null;
  const s = [...values].sort((a, b) => a - b);
  const q = (p: number) => {
    const idx = (s.length - 1) * p;
    const lo = Math.floor(idx);
    const hi = Math.ceil(idx);
    return s[lo] + (s[hi] - s[lo]) * (idx - lo);
  };
  const q1 = q(0.25);
  const q3 = q(0.75);
  const iqr = q3 - q1;
  if (iqr <= 0) return null;
  const lo = q1 - 3 * iqr;
  const hi = q3 + 3 * iqr;
  if (s[0] >= lo && s[s.length - 1] <= hi) return null;
  return [Math.max(s[0], lo), Math.min(s[s.length - 1], hi)];
}

// Reduz a série pra no máximo `max` pontos, dividindo em grupos contíguos de
// tamanho ~igual e aplicando a mesma agregação (último p/ cumulativas, média
// p/ derivadas). O último grupo inclui o ponto final, então a borda direita
// do gráfico nunca "some". Não faz nada se já estiver dentro do limite.
function downsample(
  points: CleanPoint[],
  max: number,
  aggregation: ChartAggregation
): CleanPoint[] {
  if (points.length <= max) return points;
  const sorted = [...points].sort(
    (a, b) => new Date(a.captured_at).getTime() - new Date(b.captured_at).getTime()
  );
  const n = sorted.length;
  const out: CleanPoint[] = [];
  for (let i = 0; i < max; i++) {
    const start = Math.floor((i * n) / max);
    const end = Math.floor(((i + 1) * n) / max);
    const group = sorted.slice(start, Math.max(end, start + 1));
    if (group.length === 0) continue;
    if (aggregation === "last") {
      out.push(group[group.length - 1]);
    } else {
      const avg = group.reduce((acc, p) => acc + p.value, 0) / group.length;
      out.push({ captured_at: group[group.length - 1].captured_at, value: avg });
    }
  }
  return out;
}

export function ChannelChart({
  title,
  data,
  kind = "line",
  color = "#4f8cff",
  formatValue = defaultFormat,
  period = "all",
  aggregation = "last",
  clampOutliers = false,
}: Props) {
  const cleanRaw: CleanPoint[] = data
    .filter((p) => p.value !== null && p.captured_at)
    .map((p) => ({ captured_at: p.captured_at!, value: p.value as number }));

  const inPeriod =
    period === "all" ? cleanRaw : filterPeriod(cleanRaw, period === "7d" ? 7 : 30);

  // Teto de pontos: histórico longo no modo "Todos" nunca renderiza mais que
  // MAX_POINTS (reamostra preservando o formato da curva e o último ponto).
  const capped = downsample(inPeriod, MAX_POINTS, aggregation);

  const clean = capped.map((p) => ({ ...p, label: formatDateTime(p.captured_at) }));

  if (clean.length === 0) {
    return (
      <div className="analytics-chart-box">
        <div className="analytics-chart-title">{title}</div>
        <div className="analytics-empty-chart">coletando dados…</div>
      </div>
    );
  }

  // Média do período exibido (sobre os pontos já reamostrados/plotados).
  const avgValue =
    clean.reduce((acc, p) => acc + p.value, 0) / clean.length;

  const yDomain = clampOutliers ? robustDomain(clean.map((p) => p.value)) : null;

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
            domain={yDomain ?? undefined}
            allowDataOverflow={yDomain != null}
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
      <div className="analytics-chart-avg">
        média do período: <strong>{formatValue(avgValue)}</strong>
      </div>
    </div>
  );
}
