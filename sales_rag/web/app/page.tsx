"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Result = {
  chart: string;
  columns: string[];
  rows: string[][];
  sql: string;
};

type Turn = Result & {
  question: string;
};

const PIE_COLORS = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];
const STACK_COLORS = ["#fecaca", "#fb7185", "#ef4444", "#b91c1c"];

function chartPoints(result: Result) {
  if (result.rows.length === 0 || result.rows[0].length < 2) return [];
  return result.rows.flatMap((row) => {
    const value = Number(row[1]);
    if (!Number.isFinite(value)) return [];
    return [{ label: row[0], value }];
  });
}

function isNumber(value: string) {
  return value.trim() !== "" && Number.isFinite(Number(value));
}

function seriesPoints(result: Result) {
  const { columns, rows } = result;
  if (rows.length === 0 || columns.length < 2) {
    return { points: [] as Record<string, string | number>[], series: [] as string[] };
  }

  const long =
    columns.length >= 3 &&
    rows.some((row) => !isNumber(row[1] ?? "")) &&
    rows.some((row) => isNumber(row[2] ?? ""));

  if (long) {
    const series: string[] = [];
    const byLabel = new Map<string, Record<string, string | number>>();
    for (const row of rows) {
      const name = row[1] || "Series";
      const value = Number(row[2]);
      if (!Number.isFinite(value)) continue;
      if (!series.includes(name) && series.length < 4) series.push(name);
      if (!series.includes(name)) continue;
      const point = byLabel.get(row[0]) ?? { label: row[0] };
      point[name] = value;
      byLabel.set(row[0], point);
    }
    return { points: [...byLabel.values()], series };
  }

  const series = columns
    .slice(1, 5)
    .filter((name, index) => rows.some((row) => isNumber(row[index + 1] ?? "")));
  const points = rows.flatMap((row) => {
    const point: Record<string, string | number> = { label: row[0] };
    let any = false;
    for (const name of series) {
      const value = Number(row[columns.indexOf(name)]);
      if (!Number.isFinite(value)) continue;
      point[name] = value;
      any = true;
    }
    return any ? [point] : [];
  });
  return { points, series };
}

function quarterRank(name: string) {
  const match = name.match(/q(?:uarter)?\s*([1-4])/i);
  return match ? Number(match[1]) : 100;
}

function orderedSeries(names: string[]) {
  return [...names].sort((a, b) => quarterRank(a) - quarterRank(b) || names.indexOf(a) - names.indexOf(b));
}

function compactNumber(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n)}`;
}

function EmptyChart({ chart }: { chart: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Chart</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        The query did not return the columns this {chart} chart needs.
      </CardContent>
    </Card>
  );
}

function numericIndexes(result: Result) {
  return result.columns
    .map((name, index) => ({ name, index }))
    .filter(
      ({ index }) => result.rows.filter((row) => isNumber(row[index] ?? "")).length >= 2,
    );
}

function scatterPoints(result: Result) {
  const numeric = numericIndexes(result);
  if (numeric.length < 2) return { points: [], series: [] as string[], xName: "", yName: "" };
  const x = numeric[0];
  const y = numeric[1];
  const seriesCol = result.columns.findIndex(
    (_, index) => index !== x.index && index !== y.index && result.rows.some((row) => !isNumber(row[index] ?? "")),
  );
  const points = result.rows.flatMap((row) => {
    const xv = Number(row[x.index]);
    const yv = Number(row[y.index]);
    if (!Number.isFinite(xv) || !Number.isFinite(yv)) return [];
    return [{ x: xv, y: yv, series: seriesCol >= 0 ? row[seriesCol] || "Series" : y.name }];
  });
  return { points, series: [...new Set(points.map((point) => point.series))], xName: x.name, yName: y.name };
}

function bulletRows(result: Result) {
  const numeric = numericIndexes(result);
  if (numeric.length < 2) return [];
  const labelIndex = result.columns.findIndex((_, index) => !numeric.some((col) => col.index === index));
  return result.rows.flatMap((row) => {
    const actual = Number(row[numeric[0].index]);
    const target = Number(row[numeric[1].index]);
    if (!Number.isFinite(actual) || !Number.isFinite(target)) return [];
    return [{ label: labelIndex >= 0 ? row[labelIndex] : "", actual, target }];
  });
}

function quartile(sorted: number[], p: number) {
  const index = (sorted.length - 1) * p;
  const low = Math.floor(index);
  const high = Math.ceil(index);
  if (low === high) return sorted[low];
  return sorted[low] * (high - index) + sorted[high] * (index - low);
}

function boxGroups(result: Result) {
  const numeric = numericIndexes(result);
  if (numeric.length === 0) return [];
  const valueIndex = numeric[0].index;
  const labelIndex = result.columns.findIndex((_, index) => index !== valueIndex && !numeric.some((col) => col.index === index));
  const groups = new Map<string, number[]>();
  for (const row of result.rows) {
    const value = Number(row[valueIndex]);
    if (!Number.isFinite(value)) continue;
    const label = labelIndex >= 0 ? row[labelIndex] || "Value" : numeric[0].name;
    const values = groups.get(label) ?? [];
    values.push(value);
    groups.set(label, values);
  }
  return [...groups.entries()].map(([label, values]) => {
    const sorted = [...values].sort((a, b) => a - b);
    return {
      label,
      min: sorted[0],
      q1: quartile(sorted, 0.25),
      median: quartile(sorted, 0.5),
      q3: quartile(sorted, 0.75),
      max: sorted[sorted.length - 1],
    };
  });
}

function pearson(pairs: [number, number][]) {
  const n = pairs.length;
  if (n < 2) return 0;
  const mx = pairs.reduce((sum, pair) => sum + pair[0], 0) / n;
  const my = pairs.reduce((sum, pair) => sum + pair[1], 0) / n;
  let num = 0;
  let dx = 0;
  let dy = 0;
  for (const [x, y] of pairs) {
    const a = x - mx;
    const b = y - my;
    num += a * b;
    dx += a * a;
    dy += b * b;
  }
  if (dx === 0 || dy === 0) return 0;
  return num / Math.sqrt(dx * dy);
}

function correlationMatrix(result: Result) {
  const cols = numericIndexes(result).filter(
    ({ index }) => result.rows.filter((row) => isNumber(row[index] ?? "")).length >= 3,
  );
  const matrix = cols.map((left) =>
    cols.map((right) => {
      const pairs = result.rows.flatMap((row) => {
        if (!isNumber(row[left.index] ?? "") || !isNumber(row[right.index] ?? "")) return [];
        return [[Number(row[left.index]), Number(row[right.index])] as [number, number]];
      });
      return pearson(pairs);
    }),
  );
  return { names: cols.map((col) => col.name), matrix };
}

function corrColor(value: number) {
  const blend = (value + 1) / 2;
  const red = Math.round(37 + blend * 185);
  const green = Math.round(99 + (1 - Math.abs(value)) * 120);
  const blue = Math.round(235 - blend * 190);
  return `rgb(${red}, ${green}, ${blue})`;
}

function StackedBars({ result }: { result: Result }) {
  const grouped = seriesPoints(result);
  const series = orderedSeries(grouped.series);
  if (grouped.points.length === 0 || series.length === 0) return <EmptyChart chart="stacked bar" />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Stacked bar chart</CardTitle>
      </CardHeader>
      <CardContent style={{ height: Math.max(320, grouped.points.length * 56) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart layout="vertical" data={grouped.points} margin={{ left: 8, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" />
            <YAxis type="category" dataKey="label" width={150} interval={0} />
            <Tooltip />
            <Legend />
            {series.map((name, index) => (
              <Bar key={name} dataKey={name} name={name} stackId="stack" fill={STACK_COLORS[index % STACK_COLORS.length]}>
                <LabelList
                  dataKey={name}
                  position="center"
                  fill={index < 2 ? "#7f1d1d" : "#ffffff"}
                  fontSize={11}
                  formatter={compactNumber}
                />
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function ScatterPlot({ result }: { result: Result }) {
  const parsed = scatterPoints(result);
  if (parsed.points.length === 0) return <EmptyChart chart="scatter" />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scatter plot</CardTitle>
      </CardHeader>
      <CardContent className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey="x" name={parsed.xName} />
            <YAxis type="number" dataKey="y" name={parsed.yName} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Legend />
            {parsed.series.map((name, index) => (
              <Scatter
                key={name}
                name={name}
                data={parsed.points.filter((point) => point.series === name)}
                fill={PIE_COLORS[index % PIE_COLORS.length]}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function DotPlot({ result }: { result: Result }) {
  const grouped = seriesPoints(result);
  if (grouped.points.length === 0 || grouped.series.length === 0) return <EmptyChart chart="dot" />;
  const labels = grouped.points.map((point) => String(point.label));
  const data = grouped.points.flatMap((point, index) =>
    grouped.series.flatMap((name) => {
      const value = Number(point[name]);
      if (!Number.isFinite(value)) return [];
      return [{ x: value, y: index, series: name }];
    }),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dot plot</CardTitle>
      </CardHeader>
      <CardContent style={{ height: Math.max(320, grouped.points.length * 36) }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ left: 8, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey="x" />
            <YAxis
              type="number"
              dataKey="y"
              domain={[-0.5, Math.max(grouped.points.length - 0.5, 0.5)]}
              ticks={grouped.points.map((_, index) => index)}
              tickFormatter={(value) => labels[Number(value)] ?? ""}
              width={150}
              interval={0}
            />
            <Tooltip />
            <Legend />
            {grouped.series.map((name, index) => (
              <Scatter
                key={name}
                name={name}
                data={data.filter((point) => point.series === name)}
                fill={PIE_COLORS[index % PIE_COLORS.length]}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function BulletChart({ result }: { result: Result }) {
  const rows = bulletRows(result);
  if (rows.length === 0) return <EmptyChart chart="bullet" />;
  const max = Math.max(...rows.flatMap((row) => [row.actual, row.target]), 1);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Bullet chart</CardTitle>
        <CardDescription>Bar is the actual value. The mark is the target.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {rows.map((row) => (
          <div key={row.label} className="grid grid-cols-[7rem_1fr] items-center gap-3">
            <span className="truncate text-sm">{row.label}</span>
            <div className="relative h-5 rounded bg-muted">
              <div
                className="absolute inset-y-1 left-0 rounded bg-[#2563eb]"
                style={{ width: `${(row.actual / max) * 100}%` }}
              />
              <div
                className="absolute inset-y-0 w-0.5 bg-foreground"
                style={{ left: `calc(${(row.target / max) * 100}% - 1px)` }}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function BoxPlot({ result }: { result: Result }) {
  const groups = boxGroups(result).sort((a, b) => quarterRank(a.label) - quarterRank(b.label));
  if (groups.length === 0) return <EmptyChart chart="box" />;
  const min = Math.min(...groups.map((group) => group.min));
  const max = Math.max(...groups.map((group) => group.max));
  const span = max - min || 1;
  const width = 640;
  const rowH = 40;
  const left = 72;
  const plotW = width - left - 16;
  const x = (value: number) => left + ((value - min) / span) * plotW;
  const height = groups.length * rowH + 24;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Box plot</CardTitle>
      </CardHeader>
      <CardContent>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Box plot">
          {groups.map((group, index) => {
            const y = 16 + index * rowH + rowH / 2;
            return (
              <g key={group.label}>
                <text x={left - 8} y={y + 4} textAnchor="end" fontSize="12">
                  {group.label}
                </text>
                <line x1={x(group.min)} x2={x(group.max)} y1={y} y2={y} stroke="#64748b" />
                <line x1={x(group.min)} x2={x(group.min)} y1={y - 8} y2={y + 8} stroke="#64748b" />
                <line x1={x(group.max)} x2={x(group.max)} y1={y - 8} y2={y + 8} stroke="#64748b" />
                <rect
                  x={x(group.q1)}
                  y={y - 10}
                  width={Math.max(x(group.q3) - x(group.q1), 1)}
                  height={20}
                  fill="#93c5fd"
                  stroke="#2563eb"
                />
                <line x1={x(group.median)} x2={x(group.median)} y1={y - 10} y2={y + 10} stroke="#1e3a8a" strokeWidth={2} />
              </g>
            );
          })}
        </svg>
      </CardContent>
    </Card>
  );
}

function CorrelationChart({ result }: { result: Result }) {
  const { names, matrix } = correlationMatrix(result);
  if (names.length < 2) return <EmptyChart chart="correlation" />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Correlation</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="border-collapse text-sm">
          <thead>
            <tr>
              <th />
              {names.map((name) => (
                <th key={name} className="px-3 py-1 text-left font-medium">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((rowName, rowIndex) => (
              <tr key={rowName}>
                <th className="pr-3 text-left font-medium">{rowName}</th>
                {matrix[rowIndex].map((value, columnIndex) => (
                  <td
                    key={names[columnIndex]}
                    className="px-3 py-2 text-center"
                    style={{ background: corrColor(value) }}
                  >
                    {value.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function ResultChart({ result }: { result: Result }) {
  const chart = result.chart;
  if (chart === "stacked") return <StackedBars result={result} />;
  if (chart === "scatter") return <ScatterPlot result={result} />;
  if (chart === "dot") return <DotPlot result={result} />;
  if (chart === "bullet") return <BulletChart result={result} />;
  if (chart === "box") return <BoxPlot result={result} />;
  if (chart === "correlation") return <CorrelationChart result={result} />;
  if (chart !== "bar" && chart !== "line" && chart !== "pie") return null;
  const grouped = chart === "line" || chart === "bar" ? seriesPoints(result) : null;
  const points = grouped ? grouped.points : chartPoints(result);
  if (points.length === 0 || (grouped && grouped.series.length === 0)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Chart</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The query did not return a label and a number, so the {chart} chart cannot be drawn.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="capitalize">{chart} chart</CardTitle>
      </CardHeader>
      <CardContent className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          {chart === "bar" ? (
            <BarChart data={grouped?.points}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" interval={0} angle={-40} textAnchor="end" height={70} />
              <YAxis />
              <Tooltip />
              <Legend />
              {grouped?.series.map((name, index) => (
                <Bar
                  key={name}
                  dataKey={name}
                  name={name}
                  fill={PIE_COLORS[index % PIE_COLORS.length]}
                />
              ))}
            </BarChart>
          ) : chart === "line" ? (
            <LineChart data={grouped?.points}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" interval={0} angle={-40} textAnchor="end" height={70} />
              <YAxis />
              <Tooltip />
              <Legend />
              {grouped?.series.map((name, index) => (
                <Line
                  key={name}
                  dataKey={name}
                  name={name}
                  stroke={PIE_COLORS[index % PIE_COLORS.length]}
                  dot
                />
              ))}
            </LineChart>
          ) : (
            <PieChart>
              <Tooltip />
              <Legend />
              <Pie data={points} dataKey="value" nameKey="label" outerRadius={100}>
                {points.map((point, index) => (
                  <Cell key={`${point.label}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          )}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function TurnView({ turn }: { turn: Turn }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-base font-medium">{turn.question}</h2>
      <ResultChart result={turn} />
      <Card>
        <CardHeader>
          <CardTitle>Rows</CardTitle>
        </CardHeader>
        <CardContent>
          {turn.rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">The query returned no rows.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b">
                    {turn.columns.map((column) => (
                      <th key={column} className="px-2 py-2 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {turn.rows.map((row, index) => (
                    <tr key={index} className="border-b last:border-0">
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex} className="px-2 py-2">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>SQL</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto font-mono text-sm leading-6">{turn.sql}</pre>
        </CardContent>
      </Card>
    </section>
  );
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [turns, pending, loading, error]);

  function newChat() {
    setTurns([]);
    setPending("");
    setQuestion("");
    setError("");
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError("");
    setPending(trimmed);
    setQuestion("");
    try {
      const history = turns.slice(-4).map((turn) => ({
        question: turn.question,
        sql: turn.sql,
        columns: turn.columns,
      }));
      const response = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, history }),
      });
      const text = await response.text();
      let data: Result & { detail?: unknown };
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        setQuestion(trimmed);
        setPending("");
        setError(text.slice(0, 400) || "The question failed.");
        return;
      }
      if (!response.ok) {
        setQuestion(trimmed);
        setPending("");
        setError(typeof data.detail === "string" ? data.detail : "The question failed.");
        return;
      }
      setTurns((current) => [...current, { question: trimmed, ...data }]);
      setPending("");
    } catch {
      setQuestion(trimmed);
      setPending("");
      setError("Could not reach the API. Start it with python -m uvicorn api:app --port 8000.");
    } finally {
      setLoading(false);
    }
  }

  const followUp = turns.length > 0;

  return (
    <main className="flex h-dvh flex-col">
      <header className="border-b px-6 py-4">
        <div className="mx-auto w-full max-w-3xl">
          <p className="text-sm text-muted-foreground">Gold warehouse</p>
          <h1 className="text-2xl font-semibold tracking-tight">Sales RAG</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            This chat stays open in the page. A follow-up uses the earlier questions. New chat clears it.
          </p>
        </div>
      </header>

      <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-6">
          {turns.length === 0 && !pending ? (
            <p className="text-sm text-muted-foreground">
              Ask a question below. The next question continues this same chat.
            </p>
          ) : null}
          {turns.map((turn, index) => (
            <TurnView key={`${turn.question}-${index}`} turn={turn} />
          ))}
          {pending ? <h2 className="text-base font-medium">{pending}</h2> : null}
          {loading && pending ? <p className="text-sm text-muted-foreground">Asking…</p> : null}
        </div>
      </div>

      <form onSubmit={onSubmit} className="border-t bg-background px-6 py-4">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Label htmlFor="question">{followUp ? "Follow-up" : "Question"}</Label>
          <div className="flex items-end gap-2">
            <Textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              className="flex-1"
              placeholder={
                followUp
                  ? "Continue this chat, for example: now show that as a grouped bar chart"
                  : "Make a bar chart of monthly sales revenue in 2021"
              }
            />
            <div className="flex flex-col gap-2">
              <Button type="submit" disabled={loading || !question.trim()}>
                {loading ? "Asking…" : followUp ? "Follow up" : "Ask"}
              </Button>
              <Button type="button" variant="outline" onClick={newChat} disabled={loading}>
                New chat
              </Button>
            </div>
          </div>
        </div>
      </form>
    </main>
  );
}
