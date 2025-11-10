#! /usr/bin/env python3

"""Module containing the datacenter API client code."""

import http
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
import requests
import urllib3


@dataclass
class ApiArgs:
    """
    API arguments

    Attributes
    ----------
    endpoint : str
        The base API endpoint
    verify_cert : bool
        If true, TLS certificates of the API are verified. (Default)
    """

    endpoint: str
    verify_cert: bool = os.getenv(
        "DATACENTER_API_VERIFY_CERT",
        "false",  # TODO: API is currently using self-signed certificate
    ).lower() in ["1", "true", "yes", "on"]


class _ApiResource(object):
    """
    Resource which can be requested through the API
    """

    def __init__(
        self: "_ApiResource", id: int, apiArgs: Optional[ApiArgs] = None
    ) -> None:
        """
        Create a new instance of an _ApiResource.

        Parameters
        ----------
        id : int
            The id of the resource of that type
        apiArgs : Optional[ApiArgs]
            The API args for requesting data belonging to this resource from the API
        """
        if type(self).__name__ == "_ApiResource":
            raise TypeError('Cannot create instance of type "_ApiResource".')
        self._id = id
        self._apiArgs = apiArgs

    @property
    def id(self: "_ApiResource") -> int:
        """
        The ID the resource for this type

        Returns
        -------
        int
            The id
        """
        return self._id

    def __repr__(self: "_ApiResource") -> str:
        return f"<{type(self).__name__} #{getattr(self, 'id')}>"

    def _get(
        self: "_ApiResource",
        path: str,
        is_retry: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Request data (HTTP-GET) from the API.

        Parameters
        ----------
        path : str
            The path (without the base path) of the API resource to request
        is_retry : bool
            Indicates that the request is being repeated after an initial (authentication) failure
        *args : Any
            Positional arguments to be forwarded to requests.get(...)
        **kwargs : Any
            The keyword arguments to be forwarded to requests.get(...)

        Returns
        -------
        Any
            The JSON payload from the API response
        """

        # TODO (re-)acquire token for authentication and include in request
        with urllib3.warnings.catch_warnings():  # type: ignore[attr-defined]
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            assert self._apiArgs, "No API arguments provided. (Cannot fetch content.)"
            username = os.getenv("DATACENTER_API_USER")
            password = os.getenv("DATACENTER_API_PASS")
            token_env_key = "DATACENTER_API_TOKEN"
            token = os.getenv(token_env_key)
            if username and password and not token:
                response = requests.post(
                    self._apiArgs.endpoint + "/login",
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(dict(username=username, password=password)),
                    verify=self._apiArgs.verify_cert,
                )
                response.raise_for_status()
                token = response.json()["access_token"]
                os.environ[token_env_key] = token
            if "headers" not in kwargs:
                kwargs["headers"] = {}
            if token:
                kwargs["headers"] |= {"Authorization": f"Bearer {token}"}
            response = requests.get(
                self._apiArgs.endpoint + path,
                *args,
                **kwargs | dict(verify=self._apiArgs.verify_cert),
            )
            if (
                response.status_code == http.HTTPStatus.UNAUTHORIZED
                and token
                and not is_retry
            ):
                # Token may have expired (re-try)
                del os.environ[token_env_key]
                kwargs["is_retry"] = True
                return self._get(path, *args, **kwargs)
            if response.status_code != http.HTTPStatus.OK:
                raise http.client.error(response.status_code, response.text)  # pyright: ignore[reportAttributeAccessIssue]
            return json.loads(response.text)


@dataclass
class Forecast:
    """
    Single forecast from the API.

    Attributes
    ----------
    timestamp : float
        Unix timestamp for the forecast
    renewable_powered : float
        Number of resources forecast to be powered by renewable energy at that timestamp
    reliability : float
        Forecast reliability as a fraction (0-1)
    """

    timestamp: float
    renewable_powered: float
    reliability: float

    @staticmethod
    def forecasts_to_dataframe(forecasts: List["Forecast"]) -> pd.DataFrame:
        """
        Convert list of forecasts to a Pandas dataframe with the corresponding columns.

        Parameters
        ----------
        forecasts : List[Forecast]
            The list of forecasts to be included in the dataframe

        Returns
        -------
        pd.DataFrame
            The dataframe containing the forecast data
        """
        timestamp = [datetime.fromtimestamp(f.timestamp) for f in forecasts]
        renewable_powered = [f.renewable_powered for f in forecasts]
        reliability = [f.reliability for f in forecasts]
        return pd.DataFrame(
            dict(
                timestamp=timestamp,
                renewable_powered=renewable_powered,
                reliability=reliability,
            )
        )

    @staticmethod
    def plot_forecasts(
        forecasts: List["Forecast"], title: Union[bool, Optional[str]] = True
    ) -> None:
        """
        Plot and show a list of forecasts using Matplotlib.

        Parameters
        ----------
        forecasts : List[Forecast]
            The list of forecasts to be plotted
        title : Union[bool, Optional[str]]
            Optional title of the figure or "Forecast" if True
        """
        try:
            import matplotlib.dates as mdates  # type: ignore[import-not-found]
            import matplotlib.pyplot as plt  # type: ignore[import-not-found]
            import matplotlib.ticker as mtick  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            print(
                "Plotting forecasts requires Matplotlib, but this module could not be loaded."
            )
            print("(Did you forget to install it?)")
            return

        df = Forecast.forecasts_to_dataframe(forecasts)
        plt.step(df["timestamp"], df["renewable_powered"], "C0")
        plt.ylim(-0.5, df["renewable_powered"].max() + 0.5)
        plt.ylabel("Renewable Powered", color="C0")
        plt.twinx()
        plt.step(df["timestamp"], df["reliability"], "C1")
        plt.ylim(-0.1, 1.1)
        plt.gca().yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))
        plt.ylabel("Reliability", color="C1")
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d.%m. %H:%M"))
        plt.gcf().autofmt_xdate()
        if title == True:  # noqa: E712
            plt.title("Forecast")
        elif title:
            plt.title(title)
        plt.tight_layout()
        plt.show()


class ForecastSource(_ApiResource):
    """Class representing a forecast source in the API."""

    # Currently unused
    def get_forecasts(self: "ForecastSource") -> Tuple[List[Forecast], float]:
        """
        Fetch forecasts from the forecast source.

        Returns
        -------
        Tuple[List[Forecast], float]
            List of forecasts and the current timestamp (determination)
        """
        forecasts = []
        forecasts_raw = self._get(f"/forecast/{self.id}")
        determination = datetime.fromisoformat(
            forecasts_raw["determination"].replace("Z", "+00:00")
        )
        determination_timestamp = determination.timestamp()
        for forecast_raw in forecasts_raw["forecast_list"]:
            forecasts.append(
                Forecast(
                    determination_timestamp + 3600 * forecast_raw["ahead_hour"],
                    forecast_raw["renewable_powered"],
                    forecast_raw["reliability"] / 100,  # Convert percent to fraction
                )
            )
        # Ensure forecasts are sorted chronologically
        return sorted(forecasts, key=lambda f: f.timestamp), determination_timestamp

    @staticmethod
    def from_links(
        links: Dict[str, Any], apiArgs: Optional[ApiArgs] = None
    ) -> Set["ForecastSource"]:
        """
        Create forecast source instances from links in the API response.

        Parameters
        ----------
        links : Dict[str, Any]
            The links from a previous API response
        apiArgs : Optional[ApiArgs]
            The optional API arguments

        Returns
        -------
        Set[ForecastSource]
            The forecast sources
        """
        forecast_sources: Set[ForecastSource] = set()
        for link in links:
            assert isinstance(link, dict)
            entity = str(link["href"]).split("/")[1]  # pyright: ignore[reportArgumentType]
            if entity == "forecast":
                forecast_id = int(str(link["href"]).split("/")[-1])  # pyright: ignore[reportArgumentType]
                forecast_sources.add(ForecastSource(forecast_id, apiArgs))
        return forecast_sources


class Site(_ApiResource):
    """Class representing a site in the API."""

    def __init__(self: "Site", id: int, apiArgs: Optional[ApiArgs] = None) -> None:
        """
        Create a new instance of a site.

        Parameters
        ----------
        id : int
            The id of the site
        apiArgs : Optional[ApiArgs]
            The optional API arguments
        """
        super().__init__(id, apiArgs)
        site = self._get(f"/sites/{self.id}")
        self.name = site["name"]
        self.location = site["location"]
        self.forecast_sources = ForecastSource.from_links(site["links"])


class Resource(_ApiResource):
    """Class representing a resource in the API."""

    # Currently unused
    def get_data(self: "Resource") -> Any:
        """Fetch the resource data.

        Returns
        -------
        Any
            The JSON payload of the API response
        """
        return self._get(f"/resources/{self.id}")

    @staticmethod
    def from_links(
        links: Dict[str, Any], apiArgs: Optional[ApiArgs] = None
    ) -> Set["Resource"]:
        """
        Create resource instances from links in the API response.

        Parameters
        ----------
        links : Dict[str, Any]
            The links from a previous API response
        apiArgs : Optional[ApiArgs]
            The optional API arguments

        Returns
        -------
        Set[Resource]
            The resources
        """
        resources: Set[Resource] = set()
        for link in links:
            assert isinstance(link, dict)
            assert all(isinstance(k, str) for k in link)
            entity = link["href"].split("/")[1]  # pyright: ignore[reportArgumentType]
            if entity == "resources":
                resource_id = int(link["href"].split("/")[-1])  # pyright: ignore[reportArgumentType]
                resources.add(Resource(resource_id, apiArgs))
        return resources


class Contract(_ApiResource):
    """
    Class representing a tenant contract in the API.
    """

    def __init__(
        self: "Contract", tenant: "Tenant", id: int, apiArgs: Optional[ApiArgs] = None
    ) -> None:
        """
        Create a new instance of a contract.

        Parameters
        ----------
        tenant : Tenant
            The tenant belonging to the contract
        id : int
            The id of the contract
        apiArgs : Optional[ApiArgs]
            The optional API arguments
        """
        super().__init__(id, apiArgs)
        contract = self._get(f"/tenants/{tenant.id}/contracts/{self.id}")
        self.resource_simultaneous_max = contract["resource_simultaneous_max"]
        self.site = Site(contract["site_id"], self._apiArgs)
        self.resources = Resource.from_links(contract["links"], self._apiArgs)
        self.forecast_sources = ForecastSource.from_links(
            contract["links"], self._apiArgs
        )


class Tenant(_ApiResource):
    """Class representing a tenant in the API."""

    def get_contracts(self: "Tenant") -> Set[Contract]:
        """
        Get the contracts associated with this tenant.

        Returns
        -------
        Set[Contract]
            The contracts for this tenant
        """
        return set(
            Contract(self, contract["contract_id"], self._apiArgs)
            for contract in self._get(f"/tenants/{self.id}/contracts")
        )


def __main() -> None:
    """
    Function called when executing module as a script.
    Fetches forecasts for a single tenant ID (first command line argument).
    (Demo only!)
    """

    tenant_id = -1
    try:
        tenant_id = int(sys.argv[1])
    except Exception:
        print(
            "Print/plot datacenter forecast using API.\n(Demo only!)",
            file=sys.stderr,
        )
        print(f"\nUsage: {Path(sys.argv[0]).name} <tenant id>\n", file=sys.stderr)
        sys.exit(1)

    endpoint_env_key = "DATACENTER_API_URL"
    if endpoint_env_key not in os.environ:
        print(f"Environment variable {endpoint_env_key} is not set!")
        sys.exit(1)
    apiArgs = ApiArgs(os.environ[endpoint_env_key])
    tenant = Tenant(tenant_id, apiArgs)
    print(f"Fetching contracts associated with tenant {tenant.id}...")
    contracts: List[Contract] = []
    try:
        contracts = list(tenant.get_contracts())
    except Exception:
        print(f"No contracts found for tenant {tenant.id}.")
        sys.exit(1)
    print(
        f"Fetching forecast sources associated with contracts {[c.id for c in contracts]}..."
    )
    forecast_sources = [f for c in contracts for f in c.forecast_sources]
    if len(forecast_sources) == 0:
        print(f"No forecast sources found for contracts {[c.id for c in contracts]}.")
        sys.exit(1)
    dfs = []
    determination_timestamp: float = -1
    for forecast_source in forecast_sources:
        forecasts, determination_timestamp = forecast_sources[0].get_forecasts()
        Forecast.plot_forecasts(forecasts, f"Forecast (Source {forecast_source.id})")
        df = Forecast.forecasts_to_dataframe(forecasts)
        df["forecast_source"] = forecast_source.id
        dfs.append(df)
    df = pd.concat(dfs)
    print(
        f"\nForecasts as of {determination_timestamp} (Unix timestamp):", df, sep="\n"
    )


if __name__ == "__main__":
    __main()
