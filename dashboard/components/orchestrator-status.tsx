"use client";

import { useEffect, useState } from "react";

type Status = {
  is_alive: boolean;
  last_poll_at: string | null;
  seconds_since_poll: number | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function OrchestratorStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    const cancelled = { current: false };
    const fetch_ = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/orchestrator/status`, { cache: "no-store" });
        if (!cancelled.current) setStatus(await res.json());
      } catch {}
    };
    fetch_();
    const id = setInterval(fetch_, 5000);
    return () => { cancelled.current = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (!status) return null;

  const displaySec = status.last_poll_at
    ? Math.floor(
        (Date.now() - new Date(status.last_poll_at.replace(" ", "T") + "Z").getTime()) / 1000
      )
    : null;

  const isAlive = status.is_alive && displaySec !== null && displaySec <= 75;
  const dotColor = isAlive ? "bg-emerald-500" : "bg-amber-500";
  const label = isAlive ? "Orchestrator running" : "Orchestrator stopped";
  const hint = displaySec !== null ? `last poll ${displaySec}s ago` : "no heartbeat yet";

  return (
    <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
      <span className="relative flex h-2.5 w-2.5">
        {isAlive && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-emerald-500/40" />
        )}
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${dotColor}`} />
      </span>
      <span className="font-medium text-[var(--foreground)]">{label}</span>
      <span>·</span>
      <span className="tabular-nums">{hint}</span>
    </div>
  );
}
