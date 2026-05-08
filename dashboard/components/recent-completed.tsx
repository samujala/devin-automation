"use client";

import { useEffect, useState } from "react";
import { api, type RecentSession } from "@/lib/api";
import { formatDuration, formatRelative, ruleColor } from "@/lib/format";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";

export default function RecentCompleted() {
  const [sessions, setSessions] = useState<RecentSession[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        const d = await api.recent(10);
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
        <CardTitle>Recently completed</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {sessions == null || sessions.length === 0 ? (
          <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">
            No completed sessions yet.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Batch</TableHead>
                <TableHead>Rule</TableHead>
                <TableHead>PR</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Finished</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.map((s) => (
                <TableRow key={s.session_id}>
                  <TableCell className="font-mono text-xs">{s.batch_key}</TableCell>
                  <TableCell>
                    <Badge variant={ruleColor(s.rule)}>{s.rule}</Badge>
                  </TableCell>
                  <TableCell>
                    {s.pr_url ? (
                      <span className="flex items-center gap-1.5">
                        <a
                          href={s.pr_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-[var(--primary)] hover:underline"
                        >
                          #{s.pr_number}
                        </a>
                        {s.merged_at && (
                          <Badge variant="merged">merged</Badge>
                        )}
                      </span>
                    ) : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums">
                    {formatDuration(s.duration_seconds)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        s.outcome === "merged"
                          ? "merged"
                          : s.outcome === "success"
                          ? "success"
                          : "destructive"
                      }
                    >
                      {s.outcome}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-[var(--muted-foreground)]">
                    {formatRelative(s.finished_at)}
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
