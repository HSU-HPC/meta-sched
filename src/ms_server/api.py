"""Module containing the HTTP API (FastAPI) for the Meta Scheduler server component."""

import asyncio
from typing import Any, List, Self, Set, Tuple

import ms_common
import uvicorn
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from ms_common.job import Spec as JobSpec
from ms_common.scheduling_decision import Deferred, SchedulingDecisionType
from ms_common.target import Target
from pydantic import BaseModel

from ms_server.job import Job
from ms_server.model import Model


class API(FastAPI):
    """
    Flask-based HTTP API for the Meta Scheduler.
    """

    def __init__(
        self: Self,
        host: str,
        port: int,
        targets: List[Target],
        model: Model,
        **kwargs: Any,
    ) -> None:
        """
        Create a new instance of the HTTP API.

        Parameters
        ----------
        host : str
            The hostname of the HTTP server (use "0.0.0.0" for public and "localhost" for private API)
        port : str
            The port of the HTTP server
        targets : List[Target]
            The targets available through the Meta Scheduler
        model : Model
            The model containing the state of the Meta Scheduler

        kwargs : Any
            Named arguments to be passed on to FastAPI
        """
        kwargs = dict(title="Meta-Scheduler API") | kwargs
        self.__host = host
        self.__port = port
        self.__targets = targets
        self.__model = model
        super().__init__(**kwargs)
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
            return await self.__model.get_job(job_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with array ID {array_id} and index {array_idx} not found.",
            )

    def set_up_endpoints(self: Self) -> None:
        """Set up the HTTP API endpoints."""

        @self.get("/version", response_model=str)
        def get_version() -> str:
            """
            Get the Meta Scheduler version name.

            Returns
            -------
            str
                The version name of the Meta Scheduler
            """
            return ms_common.__version__

        @self.get("/targets", response_model=List[Target])
        def get_targets() -> List[Target]:
            """
            Get all targets which jobs may be assigned to. (API endpoint)

            Returns
            -------
            List[Target]
                The list of all targets which jobs may be assigned to
            """
            return self.__targets

        class ScheduleRequest(BaseModel):
            available_targets: Set[str]
            job_spec: JobSpec

        # region job control
        # CREATE
        @self.post("/jobs")
        async def submit_job_array(request: ScheduleRequest) -> JSONResponse:
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
            target_ids = set([t.id for t in self.__targets])
            if any([t not in target_ids for t in request.available_targets]):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=dict(
                        status="fail",
                        data=dict(prefix="Unknown target(s)"),
                    ),
                )
            array_id = await self.__model.create_job_array(
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
            timestamp_start: int | None = Query(None),
            timestamp_end: int | None = Query(None),
        ) -> None:
            """
            Notify the API about a change to the jobs state. (API endpoint)

            Parameters
            ----------
            array_id : str
                The ID of the job array
            array_idx : int
                The index of the job within the array
            timestamp_start : int | None
                The start time of the job as a unix timestamp (seconds since epoch), or None if the job has not started yet
            timestamp_end : int | None
                The end time of the job as a unix timestamp (seconds since epoch), or None if the job has not ended yet
            """
            if (timestamp_start is None and timestamp_end is None) or (
                timestamp_start is not None and timestamp_end is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Either "timestamp_start" or "timestamp_end" must be provided, but not both.',
                )
            job = await self.get_job(array_id, array_idx)
            try:
                if timestamp_start is not None:
                    await job.set_timestamp_start(timestamp_start)
                if timestamp_end is not None:
                    await job.set_timestamp_end(timestamp_end)
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
                await self.__model.remove_job(job_id)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job with array ID {array_id} and index {array_idx} not found.",
                )

        # endregion job control

    def serve(self: Self) -> Tuple[uvicorn.Server, asyncio.Task[Any]]:
        """Start the HTTP API  (non-blocking).

        Returns
        -------
        Tuple[uvicorn.Server, asyncio.Task]
            The HTTP server and corresponding asyncio task
        """
        config = uvicorn.Config(
            self,
            host=self.__host,
            port=self.__port,
            workers=1,  # NOTE: Shared memory only works with a single process
        )
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        return server, server_task
