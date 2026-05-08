"use client";

import { useEffect, useState } from "react";
import { api, type LiveSession } from "@/lib/api";
import { formatDuration, formatRelative, ruleColor } from "@/lib/format";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";

function ElapsedCell({ seconds }: { seconds: number }) {
  const [tick, setTick] = useState(seconds);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return <>{formatDuration(tick)}</>;
}

export default function LiveSessions() {
  const [sessions, setSessions] = useState<LiveSession[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        const d = await api.live();
        if (!cancelled) setSessions(d);
      } catch {}
    };
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Live sessions
          {sessions != null && (
            <Badge variant={sessions.length > 0 ? "default" : "outline"}>
              {sessions.length}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {sessions == null || sessions.length === 0 ? (
          <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">
            No sessions running. System is idle.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Batch</TableHead>
                <TableHead>Rule</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Elapsed</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Devin</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.map((s) => (
                <TableRow key={s.session_id}>
                  <TableCell className="font-mono text-xs">{s.batch_key}</TableCell>
                  <TableCell>
                    <Badge variant={ruleColor(s.rule)}>{s.rule}</Badge>
                  </TableCell>
                  <TableCell className="text-xs text-[var(--muted-foreground)]">
                    {formatRelative(s.started_at)}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    <ElapsedCell seconds={s.elapsed_seconds} />
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-wrap gap-1">
                      <Badge variant="outline">{s.status}</Badge>
                      {s.status_enum && <Badge variant="slate">{s.status_enum}</Badge>}
                    </span>
                  </TableCell>
                  <TableCell>
                    {s.session_url ? (
                      <a
                        href={s.session_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-[var(--primary)] hover:underline"
                      >
                        View →
                      </a>
                    ) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
