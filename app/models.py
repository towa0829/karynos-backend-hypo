import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from database import Base

class Dreamer(Base):
    __tablename__ = "dreamers"
    dreamer_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_family = Column(String, nullable=False)
    name_given  = Column(String, nullable=False)
    created_at  = Column(DateTime, default=datetime.now)

class Job(Base):
    __tablename__ = "jobs"
    job_id      = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    salary      = Column(Integer, default=0)
    age         = Column(Integer, default=0)
    imgs        = Column(ARRAY(String), default=[])

class History(Base):
    __tablename__ = "histories"
    history_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dreamer_id  = Column(UUID(as_uuid=True), nullable=False)
    job_id      = Column(Integer, ForeignKey("jobs.job_id"), nullable=False)
    good        = Column(Boolean, default=False)
    bad         = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.now)

class DreamerProfile(Base):
    __tablename__ = "dreamer_profiles"
    dreamer_id  = Column(UUID(as_uuid=True), primary_key=True)
    job_scores  = Column(JSONB, default=list)
    updated_at  = Column(DateTime, default=datetime.now)
