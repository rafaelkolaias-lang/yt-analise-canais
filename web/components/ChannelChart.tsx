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

// 'all' devolve a série bruta. 1/7/30 = quantos dias cada bucket cobre.
export type ChartBucket = "all" | "1d" | "7d" | "30d";

// Para métricas cumulativas (views, inscritos) usamos o último valor do bucket;
// para derivadas (VPD, uploads/sem) usamos a média.
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
  bucket?: ChartBucket;
  aggregation?: ChartAggregation;
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

function formatDateOnly(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

type CleanPoint = { captured_at: string; value: number };

// Agrega pontos em buckets de N dias contados a partir do mais recente do array
// (não do "agora" do cliente — assim evita buckets vazios na borda quando há
// snapshots espaçados). Critério dentro do bucket vem do `aggregation`:
// 'last' = último valor do bucket, 'avg' = média.
function bucketize(points: CleanPoint[], bucketDays: number, aggregation: ChartAggregation): CleanPoint[] {
  if (points.length === 0) return points;
  const bucketMs = bucketDays * 24 * 60 * 60 * 1000;
  const sorted = [...points].sort(
    (a, b) => new Date(a.captured_at).getTime() - new Date(b.captured_at).getTime()
  );
  const anchor = new Date(sorted[sorted.length - 1].captured_at).getTime();

  const buckets = new Map<number, CleanPoint[]>();
  for (const p of sorted) {
    const t = new Date(p.captured_at).getTime();
    // bucketIndex 0 = bucket mais recente (cobrindo até o anchor).
    const idx = Math.floor((anchor - t) / bucketMs);
    const arr = buckets.get(idx);
    if (arr) arr.push(p);
    else buckets.set(idx, [p]);
  }

  const indexes = [...buckets.keys()].sort((a, b) => b - a); // mais antigo → mais recente
  const out: CleanPoint[] = [];
  for (const idx of indexes) {
    const arr = buckets.get(idx)!;
    if (aggregation === "last") {
      const last = arr[arr.length - 1];
      out.push(last);
    } else {
      const avg = arr.reduce((acc, p) => acc + p.value, 0) / arr.length;
      out.push({ captured_at: arr[arr.length - 1].captured_at, value: avg });
    }
  }
  return out;
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
  bucket = "all",
  aggregation = "last",
}: Props) {
  const cleanRaw: CleanPoint[] = data
    .filter((p) => p.value !== null && p.captured_at)
    .map((p) => ({ captured_at: p.captured_at!, value: p.value as number }));

  const aggregated =
    bucket === "all"
      ? cleanRaw
      : bucketize(cleanRaw, bucket === "1d" ? 1 : bucket === "7d" ? 7 : 30, aggregation);

  // Teto de pontos: mesmo no modo "Todos" (ou em buckets curtos com longo
  // histórico), nunca renderiza mais que MAX_POINTS.
  const capped = downsample(aggregated, MAX_POINTS, aggregation);

  // Em buckets diários ou maiores não precisa mostrar hora — fica menos poluído.
  const labelFn = bucket === "all" ? formatDateTime : formatDateOnly;
  const clean = capped.map((p) => ({ ...p, label: labelFn(p.captured_at) }));

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
      <div className="analytics-chart-avg">
        média do período: <strong>{formatValue(avgValue)}</strong>
      </div>
    </div>
  );
}
