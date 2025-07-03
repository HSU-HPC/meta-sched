"""Module containing the model interface for the Meta Scheduler server component."""

from typing import Any, Dict, List, Optional, Self, Set

import zmq
from ms_common.schemas import JobKey, SchedulingDecisionType
from ms_common.schemas import Spec as JobSpec
from pydantic import BaseModel
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import (AsyncAttrs, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from sqlalchemy.orm import DeclarativeBase, relationship
from zmq.asyncio import Context, Socket

from ms_server.model import Job as JobSchema
from ms_server.model import Model


class _Base(AsyncAttrs, DeclarativeBase):
    pass


class JobArray(_Base):
    __tablename__ = "job_arrays"

    id = Column(Integer, primary_key=True, index=True)
    jobs = relationship("Job", back_populates="job_array", cascade="all, delete-orphan")


class Job(_Base):
    __tablename__ = "jobs"

    token = Column(String, primary_key=True)
    array_id = Column(Integer, ForeignKey("job_arrays.id"), primary_key=True)
    array_idx = Column(Integer, primary_key=True)
    spec = Column(JSON, nullable=False)
    available_targets = Column(JSON, nullable=False)
    scheduling_decision = Column(JSON, nullable=True, default=None)
    timestamp_start = Column(Integer, nullable=True, default=None)
    timestamp_end = Column(Integer, nullable=True, default=None)

    job_array = relationship("JobArray", back_populates="jobs")


class DataBase(Model):
    def __init__(self: Self, db_url: str) -> None:
        prefix, suffix = db_url.split("://")
        match prefix:
            case "sqlite":
                prefix += "+aiosqlite"
            case "postgresql":
                prefix += "+asyncpg"
            case _:
                raise ValueError("Invalid db_url prefix", prefix)
        db_url = f"{prefix}://{suffix}"
        connect_args = dict(
            check_same_thread=False
        )  # SQLite compatibility for SQLAlchemy
        self.__engine = create_async_engine(
            db_url,
            connect_args=connect_args,
        )
        self.__make_async_session = async_sessionmaker(
            self.__engine, expire_on_commit=False
        )

        self.__ctx = Context()
        self.__pub_socket: Socket = self.__ctx.socket(zmq.PUB)
        self.__pub_port = self.__pub_socket.bind_to_random_port("tcp://*")

    async def init_models(self: Self) -> None:
        async with self.__engine.begin() as connection:
            await connection.run_sync(_Base.metadata.create_all)

    async def dispose(self: Self) -> None:
        await self.__engine.dispose()

    async def create_job_array(
        self: Self, spec: JobSpec, available_targets: Set[str], token: str
    ) -> int:
        async with self.__make_async_session() as session:
            async with session.begin():
                job_array = JobArray(
                    jobs=[
                        Job(
                            token=token,
                            array_idx=i,
                            spec=spec.model_dump(),
                            available_targets=list(available_targets),
                        )
                        for i in range(spec.array_size)
                    ]
                )
                session.add(job_array)
                await session.flush()
                await session.refresh(job_array)
            return int(job_array.id)  # pyright: ignore[reportArgumentType]

    async def get_pending_jobs(self: Self) -> List[JobSchema]:
        async with self.__make_async_session() as session:
            result = await session.execute(
                select(Job).where(Job.scheduling_decision.is_(None))
            )
            return [JobSchema.model_validate(s) for s in result.scalars().all()]

    async def __get_job(
        self: Self, job_key: JobKey, session: Optional[AsyncSession] = None
    ) -> Job:
        should_close_session = session is None
        if session is None:
            session = self.__make_async_session()
        try:
            result = await session.execute(
                select(Job).where(
                    (Job.token == job_key.token)
                    & (Job.array_id == job_key.array_id)
                    & (Job.array_idx == job_key.array_idx)
                )
            )
            job = result.scalar_one_or_none()
            if job is None:
                raise KeyError(
                    f"No job with index {job_key.array_idx} array id {job_key.array_id} exists (or the wrong token was provided)."
                )
            return job
        except Exception:
            await session.rollback()
            raise
        finally:
            if should_close_session:
                await session.close()

    async def update_job(self: Self, job_key: JobKey, data: Dict[str, Any]) -> None:
        async with self.__make_async_session() as session:
            job = await self.__get_job(job_key, session)
            for k, v in data.items():
                # Convert schema to JSON serializable data structure
                if isinstance(v, BaseModel):
                    v = v.model_dump()
                setattr(job, k, v)
            await session.commit()
            await session.refresh(job)
            job_json = JobSchema.model_validate(job).model_dump_json()
        self.__pub_socket.send_string(f"job:{job_key} {job_json}")

    async def remove_job(self: Self, job_key: JobKey) -> None:
        async with self.__make_async_session() as session:
            job = await self.__get_job(job_key, session)
            async with session.begin():
                await session.delete(job)

    async def await_scheduling_decision(
        self: Self, job_key: JobKey
    ) -> SchedulingDecisionType:
        with self.__ctx.socket(zmq.SUB) as socket:
            socket.connect(f"tcp://localhost:{self.__pub_port}")
            topic = f"job:{job_key}"
            socket.setsockopt_string(zmq.SUBSCRIBE, topic)
            job = JobSchema.model_validate(await self.__get_job(job_key))
            decision = job.scheduling_decision
            while decision is None:
                topic_received, job_json = (await socket.recv_string()).split(" ", 1)
                assert topic_received == topic
                decision = JobSchema.model_validate_json(job_json).scheduling_decision
            return decision
