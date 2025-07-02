# app/api/endpoints.py

from fastapi import APIRouter, Request
from app.services.slack_service import app_handler

router = APIRouter()

@router.post("/slack/events")
async def slack_events_endpoint(req: Request):
    """
    This is the single endpoint that Slack will send all events to.
    The slack_bolt app_handler will take care of signature verification
    and routing the event to the correct listener.
    """
    return await app_handler.handle(req)