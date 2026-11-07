"""Callable boundaries of the public Freebox SDK 1.3.1.

These protocols describe the existing calls, not a guaranteed response shape.
Raw results remain object and readers must validate them. No transport, session,
identity conversion, new endpoint or polling is introduced here.
"""
from typing import Protocol


class HomeEndpoints(Protocol):
    async def get_home_endpoint_value(self, node_id: object, endpoint_id: int) -> object:
        """Read the existing Home endpoint with an untrusted response."""
        ...

    async def set_home_endpoint_value(
        self, node_id: object, endpoint_id: int, home_endpoint_value: dict[str, object]
    ) -> object:
        """Forward the original JSON body and preserve SDK acknowledgement."""
        ...


class WifiActions(Protocol):
    async def set_global_config(self, global_configuration: dict[str, object]) -> object:
        """Use the existing global Wi-Fi endpoint."""
        ...


class CallActions(Protocol):
    async def mark_calls_log_as_read(self) -> object:
        """Use the existing calls action."""
        ...


class TvPrograms(Protocol):
    async def get_tv_programs_by_date(self, date: int | None = None) -> object:
        """Read programs without inventing a dictionary/list guarantee."""
        ...


class SystemConfiguration(Protocol):
    async def get_config(self) -> object:
        """Read system configuration; consumers validate identity/display fields."""
        ...


class LanObservations(Protocol):
    async def get_hosts_list(self, interface: str = "pub") -> object:
        ...


class WifiObservations(Protocol):
    async def get_global_config(self) -> object:
        ...

    async def get_bss(self) -> object:
        ...

    async def get_ap_list(self) -> object:
        ...

    async def get_station_list(self, ap_id: object) -> object:
        ...


class SystemActions(SystemConfiguration, Protocol):
    async def reboot(self) -> object:
        ...


class ConnectionObservations(Protocol):
    async def get_status(self) -> object:
        ...


class CallObservations(Protocol):
    async def get_calls_log(self) -> object:
        ...


class StorageObservations(Protocol):
    async def get_disks(self) -> object:
        ...

    async def get_raids(self) -> object:
        ...


class HomeObservations(Protocol):
    async def get_home_nodes(self) -> object:
        ...
