"""V2 game media services."""
from __future__ import annotations
from .common import *

class GameMediaMethods:

    async def _watchdog(self) -> None:
        try:
            while True:
                await asyncio.sleep(2)
                await self.manager.sweep_expired()
                self._schedule_tunnel_recovery()
        except asyncio.CancelledError:
            raise
