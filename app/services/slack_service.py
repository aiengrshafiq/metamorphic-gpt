# app/services/slack_service.py

import re
import requests
import json
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from threading import Thread

from app.core.config import settings
from app.services.gpt_service import gpt_service

# Initialize the Slack App with token and signing secret
slack_app = App(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET,
    # This is important for a better threading model
    process_before_response=True 
)

# This will be the handler that FastAPI uses
app_handler = SlackRequestHandler(slack_app)

# --- HELPER FUNCTIONS ---

def get_user_role(user_id: str, client):
    """
    Fetches a user's profile from Slack.
    In a real-world scenario, you would map their title or department to a role.
    For this MVP, we'll look for a "Role" custom profile field or default to 'general'.
    """
    try:
        # NOTE: You need to configure a custom profile field in Slack named "Role" for this to work.
        # Go to your workspace settings -> Customize -> Profile Fields.
        response = client.users_profile_get(user=user_id)
        profile = response.get("profile", {})
        fields = profile.get("fields", {})
        for field_id, field_data in fields.items():
            if field_data.get("label") == "Role":
                return field_data.get("value", "general").lower()
    except Exception as e:
        print(f"Error fetching user role for {user_id}: {e}")
    return "general" # Default role if not found

def process_ai_request_and_respond(body, client):
    """
    This function runs in a background thread to avoid timeouts.
    It gets the AI's answer and sends it back to Slack.
    """
    response_url = body.get("response_url")
    user_id = body.get("user_id")
    user_question = body.get("text")
    channel_id = body.get("channel_id")
    
    try:
        # Clean up the question if it's a mention
        if 'api_app_id' in body:
             user_question = re.sub(f"<@{body['api_app_id']}>", "", user_question).strip()

        if not user_question:
            message = "Please ask a question!"
        else:
            # Get user's role and the AI's answer
            user_role = get_user_role(user_id, client)
            message = gpt_service.get_answer(query=user_question, user_role=user_role)

    except Exception as e:
        print(f"Error processing request in background: {e}")
        message = "Sorry, I encountered an error. The engineers have been notified."

    # Use the response_url for slash commands, or the client for mentions
    if response_url:
        requests.post(response_url, headers={"Content-Type": "application/json"}, data=json.dumps({"text": message}))
    elif channel_id:
        client.chat_postMessage(channel=channel_id, text=message)


# --- SLACK EVENT LISTENERS ---

@slack_app.event("app_mention")
def handle_app_mentions(body, say, client):
    """Handles mentions of the bot in any channel."""
    # Send an immediate, temporary "thinking" message
    say(f"Hello <@{body['event']['user']}>! I'm thinking about your question...")
    
    # Prepare a payload for the background thread
    thread_payload = {
        "user_id": body['event']['user'],
        "text": body['event']['text'],
        "channel_id": body['event']['channel'],
        "api_app_id": body['api_app_id']
    }
    
    # Offload the actual processing to a background thread
    thread = Thread(target=process_ai_request_and_respond, args=(thread_payload, client))
    thread.start()

@slack_app.command("/ask-metamorphic-gpt")
def handle_slash_command(ack, body, client):
    """
    Handles the /ask-metamorphic-gpt slash command.
    Acknowledges immediately and offloads work to a thread.
    """
    # Acknowledge the command within 3 seconds with a temporary message
    ack(text="Thinking about your question, please wait...")
    
    # Offload the actual processing to a background thread
    thread = Thread(target=process_ai_request_and_respond, args=(body, client))
    thread.start()