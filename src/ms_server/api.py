"""Module containing the HTTP API (FastAPI) for the meta scheduler server component."""

import threading
from os import PathLike
from pathlib import Path
from typing import Any, List, Self

import uvicorn
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from ms_common import job
from ms_common.scheduler_interface import SchedulerInterface
from pydantic import BaseModel

from ms_server.counter import PersistentCounter


class API(FastAPI):
    """
    Flask-based HTTP API for the meta scheduler.
    """

    def __init__(
        self: Self,
        counter_file: str | PathLike[Any],
        scheduler: SchedulerInterface,
        **kwargs: Any,
    ) -> None:
        """
        Create a new instance of the HTTP API.

        Parameters
        ----------
        counter_file: str | PathLike[Any]
            The path at which to store the state of the job array counter for unique, sequential identifiers
        scheduler : SchedulerInterface
            The scheduling policy implementation to be applied
        kwargs : Any
            Named arguments to be passed on to FastAPI
        """
        kwargs = dict(title="Meta-Scheduler API") | kwargs
        super().__init__(**kwargs)
        self.__scheduler = scheduler
        self.__counter_file = Path(counter_file)
        self.__counter_file.parent.mkdir(parents=True, exist_ok=True)
        self.__counter = PersistentCounter()
        self.__counter_file.touch()
        self.__counter.load(self.__counter_file)
        self.__lock = threading.Lock()
        self.set_up_endpoints()

    def set_up_endpoints(self: Self) -> None:
        """Set up the HTTP API endpoints."""

        @self.get("/targets")
        def get_targets() -> JSONResponse:
            """
            Get all targets which jobs may be assigned to. (API endpoint)

            Returns
            -------
            JSONResponse
                THe API response containing the list of all targets which jobs may be assigned to
            """
            return JSONResponse(
                content=dict(
                    status="success",
                    data=[t.to_dict() for t in self.__scheduler.targets],
                )
            )

        @self.post("/jobs")
        def create_array_id() -> JSONResponse:
            """
            Create a new unique identifier for a new job array. (API endpoint)

            Returns
            -------
            JSONResponse
                The API response containing the new new unique identifier for a job array
            """
            counter_key = "job"
            array_id = self.__counter.get_next(counter_key).split("-")[-1]
            self.__counter.save(self.__counter_file)
            data = dict(array_id=array_id)
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=dict(status="success", data=data),
            )

        class ScheduleRequest(BaseModel):
            available_targets: List[str]
            job_spec: job.Spec

        @self.put("/jobs")  # TODO add job id to URL parameters
        def request_schedule(request: ScheduleRequest) -> JSONResponse:
            """
            Apply scheduling policy. (API endpoint)

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
            with self.__lock:  # For multi-threaded WSGI servers
                decision = self.__scheduler.request_schedule(
                    request.job_spec, request.available_targets
                )
            return JSONResponse(content=dict(status="success", data=decision.to_dict()))

    def run(self: Self, host: str, port: int) -> None:
        """Run the HTTP API using the built-in server (blocking).

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
        uvicorn.run(self, host=host, port=port)
