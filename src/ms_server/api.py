"""Module containing the HTTP API (FastAPI) for the Meta Scheduler server component."""

import asyncio
import secrets
from typing import (Any, AsyncGenerator, Awaitable, Coroutine, List, Optional,
                    Self, Set, Tuple, TypeVar)

import ms_common
import uvicorn
from fastapi import (Depends, FastAPI, Header, HTTPException, Query, Request,
                     status)
from fastapi.responses import StreamingResponse
from ms_common.schemas import JobKey, ScheduleRequest, ScheduleResponse, Target

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

        def get_job_token(x_job_token: Optional[str] = Header(None)) -> str:
            """
            Extract the job token from the current request headers.

            Parameters
            ----------
            x_job_token : str
                The job token passed using the X-Job-Token header

            Returns
            -------
            str
                The job token
            """
            if not x_job_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Required header "X-Job-Token" missing.',
                )
            return x_job_token

        # region job control
        # CREATE
        @self.post(
            "/jobs",
            response_model=ScheduleResponse,
            status_code=status.HTTP_201_CREATED,
        )
        async def submit_job_array(request: ScheduleRequest) -> ScheduleResponse:
            """
            Create a new unique identifier for a new job array. (API endpoint)

            Parameters
            ----------
            request : ScheduleRequest
                The request body containing the job specification and available targets

            Returns
            -------
            ScheduleResponse
                The id of the created job array, its size and the token required to access the jobs
            """
            target_ids = set([t.id for t in self.__targets])
            if any([t not in target_ids for t in request.available_targets]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unknown target(s)",
                )
            token = secrets.token_urlsafe(32)
            array_id = await self.__model.create_job_array(
                request.job_spec,
                available_targets=set(request.available_targets),
                token=token,
            )
            return ScheduleResponse(
                array_id=array_id,
                array_size=request.job_spec.array_size,
                token=token,
            )

        T = TypeVar("T")

        async def await_or_not_found(
            may_raise: Awaitable[T],
        ) -> T:
            """
            Await an asynchronous operation or respond with a HTTP 404 error if a KeyError was raised.

            Parameters
            ----------
            may_raise : Awaitable[T]
                The asynchronous operation to await

            Returns
            -------
            T
                The result of the asynchronous operation

            Raises
            ------
            HTTPException
                A HTTP 404 status with the details of the error if a KeyError was raised by the asynchronous operation
            """
            try:
                return await may_raise
            except KeyError as e:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(e),
                )

        # READ
        @self.get("/jobs/{array_id}/{array_idx}/scheduling_decision")
        async def get_scheduling_decision(
            array_id: int,
            array_idx: int,
            request: Request,
            token: str = Depends(get_job_token),
        ) -> StreamingResponse:
            """
            Await the final decision of the scheduler . (API endpoint)
            While the task has not been scheduled, heartbeat (JSON) lines are sent at a regular interval to keep the connection open.
            The last line of the response finally contains the scheduling decision as JSON.

            array_id : int
                The ID of the job array
            array_idx : int
                The index of the job within the array
            request : Request
                The HTTP request being processed
            token : str
                The random string required to look up the job

            Returns
            -------
            SchedulingDecisionType
                The scheduling decision for the job with the specified array ID and index
            """
            job_key = JobKey(token, array_id, array_idx)
            await_scheduling_timeout = 600  # seconds
            response_queue: asyncio.Queue[bytes] = asyncio.Queue()
            heartbeat_msg = b'{"heartbeat": true}\n'  # Must end in newline

            async def generate_heartbeat() -> None:
                """
                Generate heartbeat data at a regular interval and send it to the queue. (Asynchronous)
                """
                heartbeat_interval = 10
                try:
                    while True:
                        await asyncio.sleep(heartbeat_interval)
                        await response_queue.put(heartbeat_msg)
                except asyncio.CancelledError:
                    pass

            task_heartbeat = asyncio.create_task(generate_heartbeat())

            async def await_scheduling_decision() -> None:
                """
                Await the scheduling decision and send it to the queue. (Asynchronous)
                """
                try:
                    decision = await asyncio.wait_for(
                        await_or_not_found(
                            self.__model.await_scheduling_decision(job_key)
                        ),
                        timeout=await_scheduling_timeout,
                    )
                except asyncio.TimeoutError:
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    )
                await response_queue.put(decision.model_dump_json().encode("utf-8"))

            task_await_scheduling = asyncio.create_task(await_scheduling_decision())

            async def response_generator() -> AsyncGenerator[bytes, None]:
                """
                Generate returning data (lines of JSON documents) from the queue to be streamed as the response to the HTTP request. (Asynchronous)

                Returns
                -------
                AsyncGenerator[bytes, None]
                    The asynchronous generator for the StreamingResponse of the endpoint
                """
                try:
                    while True:
                        message = await response_queue.get()
                        yield message
                        if message != heartbeat_msg:
                            break  # Actual data was sent -> stop
                finally:
                    task_heartbeat.cancel()
                    task_await_scheduling.cancel()
                    await asyncio.gather(
                        task_heartbeat, task_await_scheduling, return_exceptions=True
                    )

            return StreamingResponse(
                response_generator(), media_type="application/x-ndjson"
            )

        # UPDATE
        @self.put(
            "/jobs/{array_id}/{array_idx}", status_code=status.HTTP_204_NO_CONTENT
        )
        async def update_job_time(
            array_id: int,
            array_idx: int,
            timestamp_start: Optional[int] = Query(None),
            timestamp_end: Optional[int] = Query(None),
            token: str = Depends(get_job_token),
        ) -> None:
            """
            Notify the API about a change to the jobs state. (API endpoint)

            Parameters
            ----------
            array_id : int
                The ID of the job array
            array_idx : int
                The index of the job within the array
            timestamp_start : Optional[int]
                The start time of the job as a unix timestamp (seconds since epoch), or None if the job has not started yet
            timestamp_end : Optional[int]
                The end time of the job as a unix timestamp (seconds since epoch), or None if the job has not ended yet
            token : str
                The random string required to look up the job
            """
            if (timestamp_start is None and timestamp_end is None) or (
                timestamp_start is not None and timestamp_end is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Either "timestamp_start" or "timestamp_end" must be provided, but not both.',
                )
            job_key = JobKey(token, array_id, array_idx)
            update_data = dict()
            if timestamp_start is not None:
                update_data = dict(timestamp_start=timestamp_start)
            elif timestamp_end is not None:
                update_data = dict(timestamp_end=timestamp_end)
            else:
                raise RuntimeError("Unreachable code was reached somehow")
            await await_or_not_found(self.__model.update_job(job_key, update_data))

        @self.post(
            "/jobs/{array_id}/{array_idx}/reschedule",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        async def reschedule_job(
            array_id: int,
            array_idx: int,
            available_targets: Set[str],
            token: str = Depends(get_job_token),
        ) -> None:
            """
            Reschedule a job by its array ID and index. (API endpoint)

            Parameters
            ----------
            array_id : int
                The ID of the job array
            array_idx : int
                The index of the job within the array
            available_targets : Set[str]
                The new set of target IDs which this job may be assigned to
            token : str
                The random string required to look up the job
            """
            job_key = JobKey(token, array_id, array_idx)
            await await_or_not_found(
                self.__model.update_job(
                    job_key,
                    dict(
                        timestamp_start=None,
                        timestamp_end=None,
                        available_targets=available_targets,
                        scheduling_decision=None,
                    ),
                )
            )

        # DELETE
        @self.delete("/jobs/{array_id}/{array_idx}")
        async def cancel_job(
            array_id: int, array_idx: int, token: str = Depends(get_job_token)
        ) -> None:
            """
            Cancel a job by its array ID and index. (API endpoint)

            Parameters
            ----------
            array_id : int
                The ID of the job array
            array_idx : int
                The index of the job within the array
            token : str
                The random string required to look up the job
            """
            job_key = JobKey(token, array_id, array_idx)
            await await_or_not_found(self.__model.remove_job(job_key))

        # endregion job control

    def serve(self: Self) -> Tuple[uvicorn.Server, Coroutine[Any, Any, None]]:
        """Start the HTTP API  (non-blocking).

        Returns
        -------
        Tuple[uvicorn.Server, CoroutineType[Any,Any,None]]
            The HTTP server and corresponding asyncio task
        """
        config = uvicorn.Config(
            self,
            host=self.__host,
            port=self.__port,
            workers=1,  # NOTE: SQLite only works with a single process
        )
        server = uvicorn.Server(config)
        return server, server.serve()
