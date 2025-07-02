# app/services/slack_service.py

import re
import requests
import json
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from threading import Thread

from app.core.config import settings
from app.services.gpt_service import gpt_service

# Initialize the Slack App.
# By NOT setting 'process_before_response=True', we ensure that ack()
# responds to Slack immediately, preventing timeouts.
slack_app = App(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET,
)

# This will be the handler that FastAPI uses
app_handler = SlackRequestHandler(slack_app)

# --- HELPER FUNCTIONS ---



def get_user_role(user_id: str, client):
    """
    Fetches a user's profile from Slack to determine their role.
    Includes enhanced error logging.
    """
    try:
        response = client.users_profile_get(user=user_id)
        profile = response.get("profile", {})
        fields = profile.get("fields", {})
        for field_id, field_data in fields.items():
            if field_data.get("label") == "Role":
                # Found the role, return it
                return field_data.get("value", "general").lower()
        # If the loop finishes without finding the 'Role' field
        print(f"User {user_id} profile checked, but 'Role' field not found.")
        return "general"
    except SlackApiError as e:
        # This is the new, important logging part.
        # It will print the exact error from Slack (e.g., 'missing_scope').
        print(f"Slack API Error fetching user role for {user_id}: {e.response['error']}")
    except Exception as e:
        print(f"A non-API error occurred fetching user role for {user_id}: {e}")
    
    return "general"

def process_ai_request_and_respond(payload, client):
    """
    This function runs in a background thread to do the heavy lifting.
    It now accepts a simple dictionary `payload` instead of a complex object.
    """
    response_url = payload.get("response_url")
    user_id = payload.get("user_id")
    user_question = payload.get("text")
    channel_id = payload.get("channel_id")
    
    try:
        if 'api_app_id' in payload:
             user_question = re.sub(f"<@{payload['api_app_id']}>", "", user_question).strip()

        if not user_question:
            message = "It looks like you didn't ask a question. Please try again!"
        else:
            user_role = get_user_role(user_id, client)
            message = gpt_service.get_answer(query=user_question, user_role=user_role)

    except Exception as e:
        print(f"Error processing request in background: {e}")
        message = "Sorry, I encountered an error while processing your request. The engineers have been notified."

    # Use the response_url to post the final answer back to the channel.
    if response_url:
        requests.post(response_url, headers={"Content-Type": "application/json"}, data=json.dumps({"text": message}))
    elif channel_id:
        # Fallback for app mentions which don't have a response_url
        client.chat_postMessage(channel=channel_id, text=message)


# --- SLACK EVENT LISTENERS ---

@slack_app.event("app_mention")
def handle_app_mentions(ack, body, say, client):
    """Handles mentions of the bot. Acknowledges and then processes."""
    ack() # Acknowledge the event immediately
    
    # Send an immediate, temporary "thinking" message
    say(f"Hello <@{body['event']['user']}>! I'm thinking about your question...")
    
    # Create a simple, safe dictionary to pass to the thread
    thread_payload = {
        "user_id": body['event']['user'],
        "text": body['event']['text'],
        "channel_id": body['event']['channel'],
        "api_app_id": body['api_app_id']
    }
    
    thread = Thread(target=process_ai_request_and_respond, args=(thread_payload, client))
    thread.start()

@slack_app.command("/ask-metamorphic-gpt")
def handle_slash_command(ack, body, client):
    """
    Handles the slash command. Acknowledges immediately and offloads work.
    """
    # Acknowledge the command within 3 seconds with a temporary message visible only to the user
    ack(text="Thinking about your question, please wait...")
    
    # Create a simple, safe dictionary from the body to pass to the thread
    thread_payload = {
        "user_id": body.get("user_id"),
        "text": body.get("text"),
        "response_url": body.get("response_url")
    }
    
    # Offload the actual processing to a background thread
    thread = Thread(target=process_ai_request_and_respond, args=(thread_payload, client))
    thread.start()