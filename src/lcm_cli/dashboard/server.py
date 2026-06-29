"""FastAPI application for LCM Dashboard.

Serves the frontend SPA and provides REST + WebSocket API for
real-time LCM data visualization.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from lcm_cli.dashboard.data_bridge import DataBridge

# Path to bundled frontend static files
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "dashboard"


def create_app(bridge: DataBridge | None = None, source: Any = None) -> FastAPI:
    """Create the FastAPI application with the given DataBridge and source."""
    app = FastAPI(title="LCM Dashboard", version="1.0")
    _bridge = bridge or DataBridge()
    _source = source

    # Allow cross-origin access (e.g. accessing dashboard from another machine)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Favicon — inline SVG data to avoid 404
    _FAVICON_SVG = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<rect width="32" height="32" rx="7" fill="#0a84ff"/>'
        b'<path d="M8 22 L12 14 L16 18 L20 10 L24 16" stroke="white" stroke-width="2.5"'
        b' fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(content=_FAVICON_SVG, media_type="image/svg+xml")

    # Serve frontend static files if built
    if _STATIC_DIR.exists() and (_STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        index_file = _STATIC_DIR / "index.html"
        if index_file.exists():
            return index_file.read_text()
        return (
            "<html><body style='font-family:sans-serif;text-align:center;padding:80px'>"
            "<h1>LCM Dashboard</h1>"
            "<p>Frontend not built. Run: "
            "<code>cd src/lcm_cli/dashboard/frontend && npm run build</code></p>"
            "</body></html>"
        )

    @app.get("/api/channels")
    async def list_channels() -> list[str]:
        return _bridge.get_channels()

    @app.get("/api/channels/info")
    async def list_channels_info() -> list[dict[str, Any]]:
        return _bridge.get_channels_info()

    @app.get("/api/channels/{name}/schema")
    async def get_schema(name: str) -> Any:
        schema = _bridge.get_schema(name)
        if schema is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Channel '{name}' not found or no data yet"},
            )
        return schema

    @app.get("/api/history")
    async def get_history(
        channel: str = Query(...),
        fields: str = Query(...),
        t_start: float | None = Query(None),
        t_end: float | None = Query(None),
    ) -> dict[str, list]:
        field_list = [f.strip() for f in fields.split(",") if f.strip()]
        data = _bridge.get_history(channel, field_list, t_start, t_end)
        # Convert tuples to JSON-serializable format
        return {f: [{"t": ts, "v": v} for ts, v in points] for f, points in data.items()}

    @app.websocket("/ws/data")
    async def ws_data(websocket: WebSocket) -> None:
        await websocket.accept()
        ws_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        _bridge.register_ws_queue(ws_id, queue)

        async def receive_subs() -> None:
            """Background task: listen for subscription messages from client."""
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                action = msg.get("action")
                if action == "subscribe":
                    _bridge.add_subscriber(
                        ws_id,
                        msg.get("channels", []),
                        msg.get("fields"),
                    )
                elif action == "unsubscribe":
                    _bridge.remove_subscriber(ws_id)

        sub_task = asyncio.create_task(receive_subs())

        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await websocket.send_json(data)
                except asyncio.TimeoutError:
                    # Check if client is still connected
                    if sub_task.done():
                        break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            sub_task.cancel()
            _bridge.remove_subscriber(ws_id)

    @app.on_event("startup")
    async def startup_event() -> None:
        """Start the data source on the running event loop."""
        loop = asyncio.get_running_loop()
        _bridge.set_loop(loop)
        if _source:
            _bridge.start_source(_source)

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        _bridge.stop()

    return app
