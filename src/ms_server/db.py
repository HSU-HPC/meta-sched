"""Module containing database specific code for the Meta Scheduler server component."""

from typing import Any, Dict, List, Optional, Self, Set

import zmq
from ms_common.schemas import JobKey, SchedulingDecisionType
from ms_common.schemas import Spec as JobSpec
from ms_common.schemas import Target
from ms_common.schemas import TargetStatus as TargetStatusSchema
from pydantic import BaseModel
from sqlalchemy import (JSON, Column, ForeignKey, Integer, String, delete,
                        select, update)
from sqlalchemy.ext.asyncio import (AsyncAttrs, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from sqlalchemy.orm import DeclarativeBase, relationship
from zmq.asyncio import Context, Socket

from ms_server.model import Job as JobSchema
from ms_server.model import Model, TargetsStatus


class _Base(AsyncAttrs, DeclarativeBase):
    """
    SQLAlchemy model base class.
    """

    pass


class TargetStatus(_Base):
    """
    SQLAlchemy model for the status of targets.

    Attributes
    ----------
    target_id : str
        The ID of the corresponding target
    status : dict
        The status of the target
    """

    __tablename__ = "targets_status"

    target_id = Column(String, primary_key=True, index=True)
    # Instead, delete the status if it becomes unknown
    status = Column(JSON, nullable=False)


class JobArray(_Base):
    """
    SQLAlchemy model for job arrays.

    Attributes
    ----------
    id : int
        Unique identifier of the job array (primary key)
    jobs : list[Job]
        The collection of Jobs that belong to this array
    """

    __tablename__ = "job_arrays"

    id = Column(Integer, primary_key=True, index=True)
    jobs = relationship("Job", back_populates="job_array", cascade="all, delete-orphan")


class Job(_Base):
    """
    SQLAlchemy model for jobs.

    Attributes
    ----------
    token : str
        Token for the job array (primary key)
    array_id : int
        The ID of the job array this job belongs to (primary key, foreign key referencing JobArray.id)
    array_idx : int
        The index of the job within its array (primary key)
    spec : dict
        The specification of the job (requirements, commands, etc.)
    available_targets : dict
        The targets that the job may be executed on
    scheduling_decision : dict or None
        The decision made by the scheduler regarding this job, if any
    timestamp_start : int or None
        The timestamp when the job started running
    timestamp_end : int or None
        The timestamp when the job finished running
    job_array : JobArray
        The job array that this job belongs to
    """

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
    """
    Database class containing the state of the Meta Scheduler server component which implements the model interface.
    """

    def __init__(self: Self, db_url: str, targets: List[Target]) -> None:
        """
        Connect to a database to use as the Meta Scheduler server model.

        Parameters
        ----------
        db_url : str
            The connection string for the database
            For SQLite use sqlite://path/to/my.db
            For PostgreSQL use postgresql://username:password@host:port/dbname
            For an ephemeral in-memory database for testing use sqlite://
        targets : List[Target]
            The targets available to the Meta Scheduler
        """
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

        self.__targets = {t.id: t for t in targets}

    async def init_models(self: Self) -> None:
        """Create the tables for the model."""
        async with self.__engine.begin() as connection:
            await connection.run_sync(_Base.metadata.create_all)

        async with self.__make_async_session() as session:
            async with session.begin():
                # Initially the status of all targets is unknown
                await session.execute(delete(TargetStatus))
                session.add_all(
                    [TargetStatus(target_id=t, status=None) for t in self.__targets]
                )

    async def dispose(self: Self) -> None:
        """Disconnect cleanly from the database."""
        await self.__engine.dispose()

    async def create_job_array(
        self: Self, spec: JobSpec, available_targets: Set[str], token: str
    ) -> int:
        """
        Create a new array of jobs for scheduling.

        Parameters
        ----------
        spec : job.Spec
            The job specification (also determines the number of jobs in the array)
        available_targets: Set[str]
            The set of targets on which the jobs may be executed
        token: str
            The token to associate with the jobs (required to look them up in the database)
        """
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
        """
        Get a list of jobs which are pending scheduling.

        Returns
        -------
        List[Job]
            The list of pending jobs
        """
        async with self.__make_async_session() as session:
            result = await session.execute(
                select(Job).where(Job.scheduling_decision.is_(None))
            )
            return [JobSchema.model_validate(s) for s in result.scalars().all()]

    async def get_decided_jobs(self: Self) -> List[JobSchema]:
        """
        Get a list of jobs for which a scheduling decision has been made.

        Returns
        -------
        List[Job]
            The list of scheduled jobs
        """
        async with self.__make_async_session() as session:
            result = await session.execute(
                select(Job).where(
                    Job.scheduling_decision.is_not(None)  # Was already scheduled
                    & Job.timestamp_end.is_(None)  # ...and must still complete
                )
            )
            return [JobSchema.model_validate(s) for s in result.scalars().all()]

    async def __get_job(
        self: Self, job_key: JobKey, session: Optional[AsyncSession] = None
    ) -> Job:
        """
        Get a job from the database by key.

        Parameters
        ----------
        job_key : JobKey
            The key of the job that should be looked up from the database
        session : Optional[AsyncSession]
            The existing database session to use (will not be closed)

        Returns
        -------
        Job
            The job from the database
        """
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
                    f"No job with index {job_key.array_idx} array ID {job_key.array_id} exists (or the wrong token was provided)."
                )
            return job
        except Exception:
            await session.rollback()
            raise
        finally:
            if should_close_session:
                await session.close()

    async def update_job(self: Self, job_key: JobKey, data: Dict[str, Any]) -> None:
        """
        Update an existing job.

        Parameters
        ----------
        job_key : JobKey
            The key of the job to be updated
        data : Dict[str, Any]
            The keys and corresponding values which should be updated at the job

        Raises
        ------
        KeyError
            If the job with the corresponding key does not exist
        """
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
        """
        Remove a job.

        Parameters
        ----------
        job_key : JobKey
            The key of the job to be deleted

        Raises
        ------
        KeyError
            If the job with the corresponding key does not exist
        """
        async with self.__make_async_session() as session:
            job = await self.__get_job(job_key, session)
            async with session.begin():
                await session.delete(job)
        self.__pub_socket.send_string(f"job:{job_key} null")

    async def await_scheduling_decision(
        self: Self, job_key: JobKey
    ) -> SchedulingDecisionType:
        """
        Await a scheduling decision for a specific job.

        Parameters
        ----------
        job_key : JobKey
            The key of the job for which to await scheduling

        Raises
        ------
        KeyError
            If the job with the corresponding key does not exist
        """
        with self.__ctx.socket(zmq.SUB) as socket:
            socket.connect(f"tcp://localhost:{self.__pub_port}")
            topic = f"job:{job_key}"
            socket.setsockopt_string(zmq.SUBSCRIBE, topic)
            job = JobSchema.model_validate(await self.__get_job(job_key))
            decision = job.scheduling_decision
            while decision is None:
                topic_received, job_json = (await socket.recv_string()).split(" ", 1)
                assert topic_received == topic
                if job_json == "null":
                    raise KeyError(
                        f"Job with index {job_key.array_idx} array ID {job_key.array_id} was deleted."
                    )
                decision = JobSchema.model_validate_json(job_json).scheduling_decision
            return decision

    async def update_targets_status(
        self: Self, target_id: str, status: TargetStatusSchema
    ) -> None:
        """
        Update the status of a target.

        Parameters
        ----------
        target_id : str
            The ID of the target for which to update the status
        status : TargetStatus
            The new last known status of the target
        """
        if target_id not in self.__targets:
            raise KeyError("No target with this ID: {target_id}")
        async with self.__make_async_session() as session:
            async with session.begin():
                await session.execute(
                    update(TargetStatus)
                    .where(TargetStatus.target_id == target_id)
                    .values(status=status.model_dump())
                )

    async def get_targets_status(
        self: Self,
    ) -> TargetsStatus:
        """
        Get all targets and their last known status.

        Returns
        -------
        TargetsStatus
            A mapping from target to last known status

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete model
        """
        async with self.__make_async_session() as session:
            targets_status = {
                str(s.target_id): None
                if s.status is None
                else TargetStatusSchema.model_validate(s.status)
                for s in (await session.execute(select(TargetStatus))).scalars().all()
            }
            assert len(targets_status) == len(self.__targets)
            return {v: targets_status[k] for k, v in self.__targets.items()}
