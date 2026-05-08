"""Pydantic response models for all API endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class MetricsResponse(BaseModel):
    total_findings: int
    issues_filed: int
    sessions_started: int
    sessions_completed: int
    sessions_in_progress: int
    sessions_failed: int
    prs_opened: int
    prs_merged: int
    success_rate: float | None
    avg_duration_seconds: int | None
    total_duration_seconds: int
    estimated_acus: float


class ThroughputPoint(BaseModel):
    date: str
    prs_opened: int
    prs_merged: int
    failed: int


class LiveSession(BaseModel):
    session_id: str
    batch_key: str
    rule: str
    title: str
    started_at: str
    elapsed_seconds: int
    status: str
    status_enum: str | None
    session_url: str | None


class RecentSession(BaseModel):
    session_id: str
    batch_key: str
    rule: str
    title: str
    pr_url: str | None
    pr_number: int | None
    duration_seconds: int | None
    outcome: str
    finished_at: str
    merged_at: str | None


class FailedByRule(BaseModel):
    rule: str
    failed_count: int


class FailedDetail(BaseModel):
    session_id: str
    batch_key: str
    rule: str
    reason: str
    session_url: str | None
    finished_at: str | None


class FailedResponse(BaseModel):
    by_rule: list[FailedByRule]
    detail: list[FailedDetail]


class OrchestratorStatus(BaseModel):
    is_alive: bool
    last_poll_at: str | None
    started_at: str | None
    poll_count: int
    seconds_since_poll: int | None


class HealthResponse(BaseModel):
    status: str
