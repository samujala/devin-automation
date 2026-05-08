"""FastAPI application — dashboard API backed by SQLite."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from api import queries
from api.schemas import (
    FailedResponse,
    HealthResponse,
    LiveSession,
    MetricsResponse,
    OrchestratorStatus,
    RecentSession,
    ThroughputPoint,
)

load_dotenv()

DB_PATH = Path(os.environ.get("DB_PATH", "data/findings.db"))
DASHBOARD_ORIGIN = os.environ.get("DASHBOARD_ORIGIN", "http://localhost:3000")

app = FastAPI(title="Auto-Remediation Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[DASHBOARD_ORIGIN, "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    with _conn() as conn:
        data = queries.get_metrics(conn)
    return MetricsResponse(**data)


@app.get("/api/sessions/throughput", response_model=list[ThroughputPoint])
def throughput(days: int = Query(default=14, ge=1, le=90)) -> list[ThroughputPoint]:
    with _conn() as conn:
        rows = queries.get_throughput(conn, days=days)
    return [ThroughputPoint(**r) for r in rows]


@app.get("/api/sessions/live", response_model=list[LiveSession])
def live_sessions() -> list[LiveSession]:
    with _conn() as conn:
        rows = queries.get_live_sessions(conn)
    return [LiveSession(**r) for r in rows]


@app.get("/api/sessions/recent", response_model=list[RecentSession])
def recent_sessions(limit: int = Query(default=10, ge=1, le=100)) -> list[RecentSession]:
    with _conn() as conn:
        rows = queries.get_recent_sessions(conn, limit=limit)
    return [RecentSession(**r) for r in rows]


@app.get("/api/sessions/failed", response_model=FailedResponse)
def failed_sessions(days: int = Query(default=14, ge=1, le=90)) -> FailedResponse:
    with _conn() as conn:
        data = queries.get_failed_sessions(conn, days=days)
    return FailedResponse(**data)


@app.get("/api/orchestrator/status", response_model=OrchestratorStatus)
def orchestrator_status() -> OrchestratorStatus:
    with _conn() as conn:
        return OrchestratorStatus(**queries.get_orchestrator_status(conn))


