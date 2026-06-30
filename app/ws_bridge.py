"""WebSocket bridge — broadcasts notification data to Iris plugin."""

import asyncio
import json
import logging

import websockets

log = logging.getLogger("iris.ws_bridge")

CLIENTS = set()
_loop = None


async def handler(websocket):
    CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.remove(websocket)


async def _serve(port):
    async with websockets.serve(handler, "localhost", port):
        log.info("WS bridge listening on port %d", port)
        await asyncio.Future()


def start(port=15501):
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_serve(port))


def broadcast(data):
    if _loop is None or not CLIENTS:
        return
    msg = json.dumps(data)

    async def _send_all():
        await asyncio.gather(
            *(c.send(msg) for c in set(CLIENTS)),
            return_exceptions=True,
        )

    asyncio.run_coroutine_threadsafe(_send_all(), _loop)
