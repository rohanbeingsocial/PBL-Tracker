"""The web server: a JSON API under /api, and the built React app (web/dist) for
everything else.

    python -m api            (http://127.0.0.1:8000)
"""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api import auth_routes, project_routes, session, staff_routes
from finder import db
from finder.embeddings import embed

log = logging.getLogger(__name__)
WEB = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the language model in the background, so the first meaning search is quick.
    threading.Thread(target=lambda: embed(["warm up"]), daemon=True).start()
    yield


app = FastAPI(title="PBL Tracker", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth_routes.router)
app.include_router(project_routes.router)
app.include_router(staff_routes.router)


@app.exception_handler(db.SessionEnded)
def session_ended(request: Request, exc: db.SessionEnded) -> JSONResponse:
    # Switched off, or the password changed after this sign-in (finder.db.transaction).
    session.end(request)
    response = JSONResponse({"detail": "Your session has ended. Please sign in again."}, status_code=401)
    response.delete_cookie(session.COOKIE, path="/")
    return response


@app.exception_handler(psycopg.Error)
def database_error(request: Request, exc: psycopg.Error) -> JSONResponse:
    state = exc.sqlstate or ""
    status = 403 if state == "42501" else 400 if state.startswith(("22", "23")) or state == "P0001" else 503
    # user_message() shows rule violations as written and logs anything else.
    return JSONResponse({"detail": db.user_message(exc)}, status_code=status)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if response.headers.get("content-disposition", "").startswith("inline"):
        # A report opened inside the project page: only our own pages may frame it.
        # The browser's PDF viewer needs no other rules.
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


if WEB.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def single_page_app(path: str):
        # Real files (the icon) as they are; every other path is a page of the React app.
        file = (WEB / path).resolve()
        if path and file.is_file() and WEB in file.parents:
            return FileResponse(file)
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return FileResponse(WEB / "index.html")
