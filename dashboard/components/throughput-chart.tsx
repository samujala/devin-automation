"use client";

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { api, type ThroughputPoint } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function ThroughputChart() {
  const [data, setData] = useState<ThroughputPoint[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        const d = await api.throughput(14);
        if (!cancelled) setData(d);
      } catch {}
    };
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>PR activity (last 14 days)</CardTitle>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }} barCategoryGap="20%" barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="prs_opened" name="PRs opened" fill="#22c55e" radius={[2, 2, 0, 0]} />
              <Bar dataKey="prs_merged" name="PRs merged" fill="#6366f1" radius={[2, 2, 0, 0]} />
              <Bar dataKey="failed"     name="Failed"     fill="#ef4444" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
