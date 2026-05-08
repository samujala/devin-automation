"use client";

import { useState, useEffect } from "react";
import { OrchestratorStatus } from "@/components/orchestrator-status";
import KpiStrip from "@/components/kpi-strip";
import ThroughputChart from "@/components/throughput-chart";
import LiveSessions from "@/components/live-sessions";
import RecentCompleted from "@/components/recent-completed";
import FailureAnalysis from "@/components/failure-analysis";

function LastUpdated() {
  const [ts, setTs] = useState<string>("");
  useEffect(() => {
    const tick = () => setTs(new Date().toLocaleTimeString());
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="text-xs text-[var(--muted-foreground)] tabular-nums">
      {ts ? `Updated ${ts}` : ""}
    </span>
  );
}

export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-[1280px] px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Devin Auto-Remediation — Apache Superset
          </h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            Static analysis remediation across the codebase.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <LastUpdated />
          <OrchestratorStatus />
        </div>
      </div>

      <div className="flex flex-col gap-6">
        <KpiStrip />
        <ThroughputChart />
        <LiveSessions />
        <RecentCompleted />
        <FailureAnalysis />
      </div>
    </main>
  );
}
