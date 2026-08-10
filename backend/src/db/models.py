import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    datasets: Mapped[list["Dataset"]] = relationship(back_populates="user")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    has_ground_truth: Mapped[bool] = mapped_column(Boolean, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imu_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    camera_model: Mapped[str | None] = mapped_column(String(64))
    calibration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="datasets")
    ground_truth_poses: Mapped[list["GroundTruthPose"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_datasets_user_created", "user_id", created_at.desc()),
        Index("ux_datasets_user_path", "user_id", "path", unique=True),
    )


class Run(Base):
    """One execution of the estimator over one dataset with one config."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    failure_frame: Mapped[int | None] = mapped_column(Integer)
    processed_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship()
    poses: Mapped[list["Pose"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_runs_dataset_created", "dataset_id", created_at.desc()),)


class Pose(Base):
    """The estimated trajectory. One row per estimated frame."""

    __tablename__ = "poses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx: Mapped[float] = mapped_column(Float, nullable=False)
    ty: Mapped[float] = mapped_column(Float, nullable=False)
    tz: Mapped[float] = mapped_column(Float, nullable=False)
    qw: Mapped[float] = mapped_column(Float, nullable=False)
    qx: Mapped[float] = mapped_column(Float, nullable=False)
    qy: Mapped[float] = mapped_column(Float, nullable=False)
    qz: Mapped[float] = mapped_column(Float, nullable=False)
    tracked_features: Mapped[int | None] = mapped_column(Integer)

    run: Mapped[Run] = relationship(back_populates="poses")

    __table_args__ = (Index("ix_poses_run_ts", "run_id", "timestamp_ns"),)


class GroundTruthPose(Base):
    """Truth poses loaded from the dataset.

    Kept in its own table rather than sharing one with estimated poses so a truth row can
    never be read back as an estimate.
    """

    __tablename__ = "ground_truth_poses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    timestamp_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx: Mapped[float] = mapped_column(Float, nullable=False)
    ty: Mapped[float] = mapped_column(Float, nullable=False)
    tz: Mapped[float] = mapped_column(Float, nullable=False)
    qw: Mapped[float] = mapped_column(Float, nullable=False)
    qx: Mapped[float] = mapped_column(Float, nullable=False)
    qy: Mapped[float] = mapped_column(Float, nullable=False)
    qz: Mapped[float] = mapped_column(Float, nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="ground_truth_poses")

    __table_args__ = (Index("ix_ground_truth_dataset_ts", "dataset_id", "timestamp_ns"),)
