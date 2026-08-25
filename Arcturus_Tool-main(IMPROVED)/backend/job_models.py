from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from .database import Base


class Job(Base):
    """
    Persists the equivalent of an in-memory TASKS[job_id] entry, so that
    Test Script Generation (and status polling) can still find a job after
    a backend restart/redeploy, not just within the lifetime of a single
    running process.

    `data` stores the full task dict (status, error, features,
    script_mappings, counts, etc.) as JSON text — this deliberately mirrors
    the existing in-memory dict structure exactly, rather than normalizing
    it into columns, so no other code that reads/writes TASKS[job_id] needs
    to change.
    """
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    data = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
