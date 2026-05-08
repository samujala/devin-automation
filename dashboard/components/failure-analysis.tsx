"use client";

import { useEffect, useState } from "react";
import { api, type FailedSessions } from "@/lib/api";
import { formatRelative, ruleColor } from "@/lib/format";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function FailureAnalysis() {
  const [data, setData] = useState<FailedSessions | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        const d = await api.failed(14);
        if (!cancelled) setData(d);
      } catch {}
    };
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const totalFailed = data?.by_rule.reduce((sum, r) => sum + r.failed_count, 0) ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Failure analysis (last 14 days)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-6 md:flex-row">
          {/* Left: by rule */}
          <div className="min-w-[180px]">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
              By rule
            </p>
            {totalFailed === 0 ? (
              <p className="text-sm text-[var(--muted-foreground)]">
                0 failures in the last 14 days. Devin&apos;s success rate on the current allow-list is 100%.
              </p>
            ) : (
              <ul className="space-y-2">
                {data?.by_rule.map((r) => (
                  <li key={r.rule} className="flex items-center gap-2">
                    <Badge variant={ruleColor(r.rule)}>{r.rule}</Badge>
                    <span className="font-mono text-sm tabular-nums">{r.failed_count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Right: detail list */}
          <div className="flex-1">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
              Recent failures
            </p>
            {!data || data.detail.length === 0 ? (
              <p className="text-sm text-[var(--muted-foreground)]">No failures to show.</p>
            ) : (
              <ul className="space-y-3">
                {data.detail.slice(0, 5).map((d) => (
                  <li key={d.session_id} className="flex flex-col gap-0.5 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge variant={ruleColor(d.rule)}>{d.rule}</Badge>
                      <span className="font-mono text-xs">{d.batch_key}</span>
                      {d.session_url && (
                        <a
                          href={d.session_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-auto text-xs text-[var(--primary)] hover:underline"
                        >
                          View →
                        </a>
                      )}
                    </div>
                    <span className="text-xs text-[var(--muted-foreground)]">
                      {d.reason} · {formatRelative(d.finished_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
