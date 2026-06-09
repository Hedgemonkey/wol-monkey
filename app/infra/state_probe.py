"""StateProbe — pragmatic multi-signal online detection (ping + TCP-SSH).

All blocking/subprocess I/O is confined to this infra module.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.domain.probe import ProbeResult

logger = structlog.get_logger(__name__)

_PING_TIMEOUT_S = 2.0
_TCP_TIMEOUT_S = 2.0
_SSH_PORT = 22


class StateProbe:
    """Probe a machine's online status using ping and TCP-SSH."""

    def __init__(
        self,
        ping_timeout: float = _PING_TIMEOUT_S,
        tcp_timeout: float = _TCP_TIMEOUT_S,
    ) -> None:
        self._ping_timeout = ping_timeout
        self._tcp_timeout = tcp_timeout

    async def probe(self, machine_id: str, host: str, ssh_port: int = _SSH_PORT) -> ProbeResult:
        ping_ok, tcp_ok = await asyncio.gather(
            self._ping(host),
            self._tcp_connect(host, ssh_port),
            return_exceptions=False,
        )
        result = ProbeResult(
            machine_id=machine_id,
            ping_ok=bool(ping_ok),
            tcp_ssh_ok=bool(tcp_ok),
            observed_at=datetime.now(UTC),
        )
        logger.debug(
            "probe_result",
            machine_id=machine_id,
            host=host,
            ping=ping_ok,
            tcp=tcp_ok,
            state=result.derived_state.value,
        )
        return result

    async def _ping(self, host: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                "1",
                "-W",
                str(int(self._ping_timeout)),
                host,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=self._ping_timeout + 1)
            return proc.returncode == 0
        except Exception:
            return False

    async def _tcp_connect(self, host: str, port: int) -> bool:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self._tcp_timeout,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False
