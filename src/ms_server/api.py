"""Module containing the HTTP API (FastAPI) for the Meta Scheduler server component."""

import asyncio
import signal
from typing import Any, List, Self, Set

import uvicorn
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from ms_common import job
from ms_common.scheduling_decision import Deferred, SchedulingDecisionType
from ms_common.target import Target
from pydantic import BaseModel

from ms_server.job import Job
from ms_server.model import Model
from ms_server.scheduling import Policy


class API(FastAPI):
    """
    Flask-based HTTP API for the Meta Scheduler.
    """

    def __init__(
        self: Self,
        scheduler: Policy,
        **kwargs: Any,
    ) -> None:
        """
        Create a new instance of the HTTP API.

        Parameters
        ----------
        scheduler : SchedulerInterface
            The scheduling policy implementation to be applied
        kwargs : Any
            Named arguments to be passed on to FastAPI
        """
        kwargs = dict(title="Meta-Scheduler API") | kwargs
        super().__init__(**kwargs)
        self.__scheduler = scheduler
        self.__state = Model()
        # TODO
        # set up scheduler and model (storing jobs)

        self.set_up_endpoints()

    async def get_job(self: Self, array_id: str, array_idx: int) -> Job:
        """
        Get a job by its array ID and index.

        Parameters
        ----------
        array_id : str
            The ID of the job array
        array_idx : int
            The index of the job within the array

        Returns
        -------
        job.Job
            The job with the specified array ID and index

        Raises
        ------
        HTTPException
            If the job with the specified array ID and index does not exist
        """
        job_id = (array_id, array_idx)
        try:
            return await self.__state.get_job(job_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with array ID {array_id} and index {array_idx} not found.",
            )

    def set_up_endpoints(self: Self) -> None:
        """Set up the HTTP API endpoints."""

        @self.get("/targets", response_model=List[Target])
        def get_targets() -> List[Target]:
            """
            Get all targets which jobs may be assigned to. (API endpoint)

            Returns
            -------
            List[Target]
                The list of all targets which jobs may be assigned to
            """
            return self.__scheduler.targets

        class ScheduleRequest(BaseModel):
            available_targets: Set[str]
            job_spec: job.Spec

        # CREATE
        @self.post("/jobs")
        async def submit(request: ScheduleRequest) -> JSONResponse:
            # TODO update doc string
            """
            Create a new unique identifier for a new job array. (API endpoint)

            Parameters
            ----------
            request : ScheduleRequest
                The request body containing the job specification and available targets

            Returns
            -------
            JSONResponse
                The API response containing the new new unique identifier for a job array
            """
            target_ids = set([t.id for t in self.__scheduler.targets])
            if any([t not in target_ids for t in request.available_targets]):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=dict(
                        status="fail",
                        data=dict(prefix="Unknown target(s)"),
                    ),
                )
            array_id = await self.__state.create_job_array(
                request.job_spec, available_targets=request.available_targets
            )
            # TODO return list of job IDs instead of array ID?
            data = dict(array_id=array_id)
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=dict(status="success", data=data),
            )

        # READ
        @self.get(
            "/jobs/{array_id}/{array_idx}/scheduling_decision",
            response_model=SchedulingDecisionType,
        )
        async def get_scheduling_decision(
            array_id: str, array_idx: int
        ) -> SchedulingDecisionType:
            """
            Poll the final decision of the scheduler or time out if it is not yet available. (API endpoint)

            Returns
            -------
            SchedulingDecisionType
                The scheduling decision for the job with the specified array ID and index
            """
            job = await self.get_job(array_id, array_idx)
            decision: SchedulingDecisionType = Deferred(
                wait_seconds=0  # May retry immediately
            )
            timeout = 30  # seconds
            try:
                decision = await asyncio.wait_for(
                    job.get_scheduling_decision(), timeout
                )
            except asyncio.TimeoutError:
                pass
            return decision

        # UPDATE

        # TODO this endpoint should be protected by authentication
        @self.put("/jobs/{array_id}/{array_idx}", status_code=204)
        async def update_job_time(
            array_id: str,
            array_idx: int,
            timestamp_started: int | None = Query(None),
            timestamp_ended: int | None = Query(None),
        ) -> None:
            """
            Notify the API about a change to the jobs state. (API endpoint)

            Parameters
            ----------
            array_id : str
                The ID of the job array
            array_idx : int
                The index of the job within the array
            timestamp_started : int | None
                The start time of the job as a unix timestamp (seconds since epoch), or None if the job has not started yet
            timestamp_ended : int | None
                The end time of the job as a unix timestamp (seconds since epoch), or None if the job has not ended yet
            """
            if (timestamp_started is None and timestamp_ended is None) or (
                timestamp_started is not None and timestamp_ended is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Either "timestamp_started" or "timestamp_ended" must be provided, but not both.',
                )
            job = await self.get_job(array_id, array_idx)
            try:
                if timestamp_started is not None:
                    await job.set_timestamp_started(timestamp_started)
                if timestamp_ended is not None:
                    await job.set_timestamp_ended(timestamp_ended)
            except AssertionError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                )

        # TODO this endpoint should be protected by authentication
        @self.post("/jobs/{array_id}/{array_idx}/reschedule", status_code=204)
        async def reschedule_job(
            array_id: str, array_idx: int, available_targets: Set[str]
        ) -> None:
            """
            Reschedule a job by its array ID and index. (API endpoint)

            Parameters
            ----------
            array_id : str
                The ID of the job array
            array_idx : int
                The index of the job within the array
            available_targets : Set[str]
                The new set of target IDs which this job may be assigned to
            """
            job = await self.get_job(array_id, array_idx)
            await job.reschedule(available_targets)

        # DELETE
        # TODO this endpoint should be protected by authentication
        @self.delete("/jobs/{array_id}/{array_idx}")
        async def cancel_job(array_id: str, array_idx: int) -> None:
            """
            Cancel a job by its array ID and index. (API endpoint)

            Parameters
            ----------
            array_id : str
                The ID of the job array
            array_idx : int
                The index of the job within the array
            """
            job_id = (array_id, array_idx)
            try:
                await self.__state.remove_job(job_id)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job with array ID {array_id} and index {array_idx} not found.",
                )

    async def scheduling_loop(self: Self) -> None:
        """
        Run the scheduling loop (non-blocking).
        """
        loop_interval = 10  # seconds # TODO make configurable
        try:
            while True:
                # TODO update jobs which have started and who must have finished, but have not been updated accordingly
                loop_start = asyncio.get_event_loop().time()
                pending_jobs = await self.__state.get_pending_jobs()
                await self.__scheduler.update(pending_jobs)
                sleep_time = max(
                    0, loop_interval - (asyncio.get_event_loop().time() - loop_start)
                )
                await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            pass

    # TODO refactor (extract API class from Server class)
    async def serve(self: Self, host: str, port: int) -> None:
        """Run the HTTP API  (non-blocking).

        Parameters
        ----------
        host : str
            The hostname of the HTTP server (use "0.0.0.0" for public and "localhost" for private API)
        port : str
            The port of the HTTP server

        Returns
        -------
        Process
            The process executing the API
        """
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        scheduler_task = asyncio.create_task(self.scheduling_loop())

        def shutdown() -> None:
            """Signal handler to shut down the scheduling loop."""
            stop_event.set()

        loop.add_signal_handler(signal.SIGINT, shutdown)
        loop.add_signal_handler(signal.SIGTERM, shutdown)
        config = uvicorn.Config(
            self,
            host=host,
            port=port,
            workers=1,  # NOTE: Shared memory only works with a single process
        )
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        await stop_event.wait()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        server.should_exit = True
        await server_task

    def run(self: Self, host: str, port: int) -> None:
        """Run the HTTP API  (blocking).

        Parameters
        ----------
        host : str
            The hostname of the HTTP server (use "0.0.0.0" for public and "localhost" for private API)
        port : str
            The port of the HTTP server

        Returns
        -------
        Process
            The process executing the API
        """
        asyncio.run(self.serve(host, port))
