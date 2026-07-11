# src/dianshang/server/jobs.py
"""内存任务存储（线程安全）。"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobStatus:
    job_id: str
    status: str = "queued"  # queued|running|done|error|cancelled
    current_node: str | None = None
    completed_nodes: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stale: bool = False


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    def set(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            self._jobs[job_id] = status

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> JobStatus | None:
        with self._lock:
            st = self._jobs.get(job_id)
            if st is None:
                return None
            for k, v in fields.items():
                setattr(st, k, v)
            return st

    def all(self) -> dict[str, JobStatus]:
        with self._lock:
            return dict(self._jobs)


job_store = JobStore()
