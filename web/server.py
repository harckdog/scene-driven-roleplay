"""ASGI entry point for the Momotalk frontend API.

The current Gradio application remains available in ``app.py`` while this new
server is introduced incrementally.  A later step will mount the built Vue
application here without changing any conversation core modules.
"""

import asyncio
from contextlib import asynccontextmanager
import logging

from config import REMINDER_MODEL_TIMEOUT_SECONDS
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from web.api import asset_directory, router


_LOGGER = logging.getLogger(__name__)


async def _deliver_alarm(alarm) -> None:
    """Append a character-written reminder, with a reliable visible fallback."""
    from core.roleplay_chatbot import generate_reminder_replies
    from roleplay.alarms import reminder_text
    from roleplay.session_manager import append

    try:
        replies = await asyncio.wait_for(
            asyncio.to_thread(generate_reminder_replies, alarm.role_id, alarm.text),
            timeout=REMINDER_MODEL_TIMEOUT_SECONDS,
        )
    except (Exception, asyncio.CancelledError) as error:
        if isinstance(error, asyncio.CancelledError):
            raise
        _LOGGER.warning("Reminder model reply failed for alarm %s: %s", alarm.id, error)
        append(alarm.role_id, "assistant", reminder_text(alarm), event_type="reminder")
        return
    for reply in replies:
        append(
            alarm.role_id,
            "assistant",
            reply.text,
            sticker_id=reply.sticker_id,
            event_type="reminder",
        )


async def _alarm_loop(background_tasks: set[asyncio.Task]) -> None:
    """Deliver due reminders while the local web server remains running."""
    from roleplay.alarms import claim_due_alarms

    while True:
        for alarm in claim_due_alarms():
            task = asyncio.create_task(_deliver_alarm(alarm), name=f"reminder-{alarm.id}")
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        await asyncio.sleep(15)


@asynccontextmanager
async def _lifespan(_application: FastAPI):
    """Run the single local reminder worker for this server process."""
    background_tasks: set[asyncio.Task] = set()
    task = asyncio.create_task(_alarm_loop(background_tasks))
    try:
        yield
    finally:
        task.cancel()
        for background_task in background_tasks:
            background_task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Create the API host and, when built, serve the Momotalk single-page UI."""
    application = FastAPI(title="scene-driven-roleplay API", lifespan=_lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    # Vue's production bundle owns /assets. Character resources intentionally
    # use a distinct prefix so a sticker route can never shadow CSS or JS.
    from pathlib import Path

    assets_root = Path(asset_directory())
    if assets_root.is_dir():
        application.mount("/local-assets", StaticFiles(directory=assets_root), name="local-assets")
    application.include_router(router)
    frontend_dist = frontend_directory()
    if frontend_dist.is_dir():
        # Mount after /api and /assets so frontend fallback never shadows them.
        application.mount("/", StaticFiles(directory=frontend_dist, html=True), name="momotalk")
    else:
        @application.get("/")
        def frontend_not_built() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "This architecture snapshot provides the API only; no frontend is bundled.",
                    "next_step": "Open /docs for the API schema.",
                }
            )
    return application


def frontend_directory():
    """Return the Vue production build directory without coupling API imports to Vite."""
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "momotalk-main" / "dist"


app = create_app()
