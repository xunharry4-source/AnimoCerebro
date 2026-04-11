from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from typing import Any, Dict, List, Optional
from zentex.web_console.contracts.runtime import TranscriptStreamMessage
from zentex.web_console.dependencies import get_weight_assembler
from zentex.web_console.services.overview import build_overview_payload
from zentex.web_console.transcript_serialization import serialize_transcript_entry


router = APIRouter()


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            return


@router.websocket("/events/stream")
async def stream_events(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime = getattr(websocket.app.state, "runtime", None)
    if runtime is None:
        await websocket.close(code=1011, reason="BrainRuntime is not attached")
        return

    session = getattr(websocket.app.state, "session", None)
    if session is not None and not hasattr(session, "advance_turn"): # Duck type check
        session = None

    last_entry_id = websocket.query_params.get("last_entry_id")
    transcript_store = runtime.transcript_store
    current_entries = transcript_store.get_entries_snapshot()
    if last_entry_id:
        last_sent_index = next(
            (index for index, entry in enumerate(current_entries) if entry.entry_id == last_entry_id),
            len(current_entries) - 1,
        )
    else:
        # Real-time stream is delta-only by default. Historical events are already
        # available via `/api/web/overview.recent_events` and replay endpoints.
        last_sent_index = len(current_entries) - 1
    last_seen_revision = transcript_store.get_revision()
    disconnect_task = asyncio.create_task(_wait_for_disconnect(websocket))

    try:
        while True:
            if disconnect_task.done():
                return

            current_entries = transcript_store.get_entries_snapshot()
            newest_index = len(current_entries) - 1
            if newest_index <= last_sent_index:
                revision_wait_task = asyncio.create_task(asyncio.to_thread(
                    transcript_store.wait_for_revision_after,
                    last_seen_revision,
                    3.0,
                ))
                done, pending = await asyncio.wait(
                    {revision_wait_task, disconnect_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if disconnect_task in done:
                    # Client disconnected — cancel the revision wait and exit.
                    # Never cancel disconnect_task here; it already finished.
                    revision_wait_task.cancel()
                    return
                # revision_wait_task completed first.
                # disconnect_task is still pending — leave it alive for the
                # remainder of this connection's lifetime.
                try:
                    updated = revision_wait_task.result()
                except Exception:
                    updated = False
                if updated:
                    last_seen_revision = transcript_store.get_revision()
                continue

            if session is None and getattr(websocket.app.state, "session", None) is not None:
                session = getattr(websocket.app.state, "session")

            overview = build_overview_payload(
                runtime,
                session,
                get_weight_assembler(websocket.app),
            )
            for entry in current_entries[last_sent_index + 1 :]:
                if disconnect_task.done():
                    return
                message = TranscriptStreamMessage(
                    event=serialize_transcript_entry(entry),
                    overview=overview,
                )
                await websocket.send_json(message.model_dump(mode="json"))
            last_sent_index = newest_index
            last_seen_revision = transcript_store.get_revision()
    except (WebSocketDisconnect, RuntimeError):
        return
    except Exception:
        return
    finally:
        disconnect_task.cancel()
