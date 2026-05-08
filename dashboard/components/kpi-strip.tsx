"use client";

import { useEffect, useState } from "react";
import { api, type Metrics } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { Card, CardHeader, CardDescription, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="font-mono text-3xl font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}

function KpiSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-16" />
      </CardContent>
    </Card>
  );
}

export default function KpiStrip() {
  const [data, setData] = useState<Metrics | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        const m = await api.metrics();
        if (!cancelled) setData(m);
      } catch {}
    };
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (!data) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => <KpiSkeleton key={i} />)}
      </div>
    );
  }

  const successPct =
    data.success_rate != null
      ? `${(data.success_rate * 100).toFixed(0)}%`
      : "—";

  const cards = [
    { label: "Issues filed",     value: String(data.issues_filed) },
    { label: "PRs opened",       value: String(data.prs_opened) },
    { label: "PRs merged",       value: String(data.prs_merged) },
    { label: "Success rate",     value: successPct },
    { label: "Avg time-to-PR",   value: formatDuration(data.avg_duration_seconds) },
    { label: "Est. ACUs spent",  value: data.estimated_acus.toFixed(1) },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {cards.map((c) => <KpiCard key={c.label} label={c.label} value={c.value} />)}
    </div>
  );
}
