
import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
import logging

from contextlib import contextmanager

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    BackgroundTasks
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .workflow import GRAPH
from .github import publish_pr
from .telegram import notify


logger = logging.getLogger(__name__)

app = FastAPI(
    title="BugPilot AI",
    version="3.1.0"
)

DB = os.getenv("DB_PATH", "/data/runs.db")
APP_ID = os.getenv("APP_ID", "buggy-app-001")


# ==========================================
# DATABASE
# ==========================================

@contextmanager
def connect():
    os.makedirs(
        os.path.dirname(DB) or ".",
        exist_ok=True
    )

    db = sqlite3.connect(DB, timeout=10)

    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                app_id TEXT,
                status TEXT,
                state TEXT,
                created REAL,
                pr_url TEXT
            )
        """)

        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def update_run(run_id, status, state):
    with connect() as db:
        db.execute(
            """
            UPDATE runs
            SET status=?, state=?
            WHERE id=?
            """,
            (
                status,
                json.dumps(state),
                run_id
            )
        )


def safe_notify(message):
    try:
        notify(message)
    except Exception:
        logger.exception(
            "Telegram notification failed"
        )


# ==========================================
# REQUEST MODELS
# ==========================================

class DemoEvent(BaseModel):
    app_id: str
    traceback: str


class Approval(BaseModel):
    approved: bool
    confirmation: str = ""


# ==========================================
# BACKGROUND INVESTIGATION
# ==========================================

def process_investigation(
    run_id: str,
    traceback_text: str
):
    started = time.perf_counter()

    state = {
        "traceback": traceback_text,
        "steps": [],
        "status": "running"
    }

    update_run(run_id, "running", state)

    logger.info(
        "Investigation started: %s",
        run_id
    )

    try:
        result = GRAPH.invoke({
            "traceback": traceback_text,
            "steps": []
        })

        status = result.get(
            "status",
            "failed"
        )

        result["duration_ms"] = round(
            (time.perf_counter() - started) * 1000,
            2
        )

        update_run(
            run_id,
            status,
            result
        )

        logger.info(
            "Investigation completed: %s status=%s",
            run_id,
            status
        )

        safe_notify(
            f"BugPilot run {run_id}: {status} — "
            f"{result.get('error_type', 'unknown')}"
        )

    except Exception as exc:

        logger.exception(
            "Investigation failed: %s",
            run_id
        )

        duration_ms = round(
            (time.perf_counter() - started) * 1000,
            2
        )

        result = {
            "traceback": traceback_text,
            "status": "failed",
            "duration_ms": duration_ms,
            "steps": [
                {
                    "name": "error",
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "detail": str(exc)
                }
            ]
        }

        update_run(
            run_id,
            "failed",
            result
        )

        safe_notify(
            f"BugPilot run {run_id}: failed"
        )


# ==========================================
# CREATE INVESTIGATION
# ==========================================

def enqueue_investigation(
    event: DemoEvent,
    background_tasks: BackgroundTasks
):
    if event.app_id != APP_ID:
        raise HTTPException(
            404,
            "Unknown application ID"
        )

    if len(event.traceback) > 12000:
        raise HTTPException(
            413,
            "Traceback too long"
        )

    run_id = uuid.uuid4().hex[:12]

    initial_state = {
        "traceback": event.traceback,
        "steps": [],
        "status": "queued"
    }

    with connect() as db:
        db.execute(
            """
            INSERT INTO runs
            (id, app_id, status, state, created, pr_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                event.app_id,
                "queued",
                json.dumps(initial_state),
                time.time(),
                None
            )
        )

    background_tasks.add_task(
        process_investigation,
        run_id,
        event.traceback
    )

    return {
        "run_id": run_id,
        "status": "queued",
        "message": "Investigation accepted"
    }


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "bugpilot-agent",
        "version": "3.1.0",
        "llm_provider": os.getenv(
            "LLM_PROVIDER",
            "groq"
        )
    }


# ==========================================
# DEMO WEBHOOK
# ==========================================

@app.post("/events/demo", status_code=202)
def demo(
    event: DemoEvent,
    background_tasks: BackgroundTasks
):
    return enqueue_investigation(
        event,
        background_tasks
    )


# ==========================================
# TRIGGER BUGGY APPLICATION
# ==========================================

@app.post("/trigger")
def trigger_demo(scenario: str = "zero"):
    import requests

    try:
        response = requests.post(
            "http://buggy-app:8001/trigger",
            params={"scenario": scenario},
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    except requests.RequestException as exc:
        raise HTTPException(
            502,
            "Buggy app unavailable: " + str(exc)
        )


# ==========================================
# LIST INVESTIGATIONS
# ==========================================

@app.get("/runs")
def runs():
    with connect() as db:
        rows = db.execute("""
            SELECT id, app_id, status, created, pr_url
            FROM runs
            ORDER BY created DESC
            LIMIT 30
        """).fetchall()

    return [
        {
            "id": row[0],
            "app_id": row[1],
            "status": row[2],
            "created": row[3],
            "pr_url": row[4]
        }
        for row in rows
    ]


# ==========================================
# INVESTIGATION DETAILS
# ==========================================

@app.get("/runs/{run_id}")
def get_run(run_id: str):

    with connect() as db:
        row = db.execute(
            """
            SELECT status, state, pr_url
            FROM runs
            WHERE id=?
            """,
            (run_id,)
        ).fetchone()

    if not row:
        raise HTTPException(
            404,
            "Not found"
        )

    state = json.loads(row[1])

    return {
        "id": run_id,
        "status": row[0],
        "steps": state.get("steps", []),
        "diff": state.get("diff", ""),
        "explanation": state.get("explanation", ""),
        "root_cause": state.get("root_cause", ""),
        "error_type": state.get("error_type", ""),
        "attempts": state.get("attempts", 0),
        "duration_ms": state.get("duration_ms", 0),
        "pr_url": row[2]
    }


# ==========================================
# HUMAN APPROVAL
# ==========================================

@app.post("/runs/{run_id}/approval")
def approve(
    run_id: str,
    decision: Approval,
    request: Request
):
    secret = os.getenv("APPROVAL_TOKEN", "")

    provided = request.headers.get(
        "X-Approval-Token",
        ""
    )

    if not secret or not hmac.compare_digest(
        provided,
        secret
    ):
        raise HTTPException(
            403,
            "Approval authentication required"
        )

    if (
        decision.approved
        and decision.confirmation != "PUBLISH PR"
    ):
        raise HTTPException(
            400,
            "Explicit confirmation PUBLISH PR required"
        )

    with connect() as db:
        row = db.execute(
            """
            SELECT status, state
            FROM runs
            WHERE id=?
            """,
            (run_id,)
        ).fetchone()

        if not row:
            raise HTTPException(404, "Not found")

        if row[0] != "awaiting_approval":
            raise HTTPException(
                409,
                "Run is not awaiting approval"
            )

        state = json.loads(row[1])

        next_status = (
            "publishing"
            if decision.approved
            else "rejected"
        )

        updated = db.execute(
            """
            UPDATE runs SET status=?
            WHERE id=? AND status='awaiting_approval'
            """,
            (next_status, run_id)
        )

        if updated.rowcount != 1:
            raise HTTPException(
                409,
                "Run already processed"
            )

    status = "rejected"
    url = None

    if decision.approved:

        try:
            url = publish_pr(
                state["patched"],
                state["revision"],
                run_id
            )

            status = "pr_created"

        except Exception as exc:

            update_run(
                run_id,
                "publish_failed",
                state
            )

            raise HTTPException(
                502,
                "GitHub publishing failed: " + str(exc)
            )

    with connect() as db:
        db.execute(
            """
            UPDATE runs
            SET status=?, pr_url=?
            WHERE id=?
            """,
            (status, url, run_id)
        )

    safe_notify(
        f"BugPilot run {run_id}: "
        f"{status} {url or ''}"
    )

    return {
        "status": status,
        "pr_url": url
    }


# ==========================================
# GITHUB WEBHOOK
# ==========================================

@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    secret = os.getenv(
        "GITHUB_WEBHOOK_SECRET",
        ""
    )

    if not secret:
        raise HTTPException(
            503,
            "GitHub webhook secret not configured"
        )

    body = await request.body()

    signature = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    provided = request.headers.get(
        "X-Hub-Signature-256",
        ""
    )

    if not hmac.compare_digest(
        signature,
        provided
    ):
        raise HTTPException(
            401,
            "Invalid signature"
        )

    event = request.headers.get(
        "X-GitHub-Event",
        ""
    )

    data = json.loads(body)

    if (
        event == "issues"
        and data.get("action") == "opened"
    ):
        issue = data.get("issue", {})
        text = issue.get("body") or ""

        if "Traceback (most recent call last)" in text:

            result = enqueue_investigation(
                DemoEvent(
                    app_id=APP_ID,
                    traceback=text[:12000]
                ),
                background_tasks
            )

            from fastapi.responses import JSONResponse

            return JSONResponse(
                content=result,
                status_code=202
            )

    return {
        "status": "ignored",
        "event": event
    }


# ==========================================
# SENTRY WEBHOOK
# ==========================================

@app.post("/webhooks/sentry")
async def sentry_webhook(request: Request):

    raise HTTPException(
        501,
        "Sentry verification/normalization "
        "not configured"
    )


# ==========================================
# DASHBOARD
# ==========================================

@app.get("/", response_class=HTMLResponse)
def index():

    with open(
        "/app/static/index.html",
        encoding="utf-8"
    ) as file:

        return file.read()
