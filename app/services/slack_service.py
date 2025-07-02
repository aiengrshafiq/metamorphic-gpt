# app/services/slack_service.py

import re
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from threading import Thread

from app.core.config import settings
from app.services.gpt_service import gpt_service

# Initialize the Slack App with token and signing secret
slack_app = App(
    token=settings.SLACK_BOT_TOKEN,
    signing_secret=settings.SLACK_SIGNING_SECRET
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

def process_request(body, say, client):
    """
    Handles the actual processing of a user's query in a separate thread
    to avoid Slack API timeouts.
    """
    try:
        user_id = body["user_id"]
        user_question = body["text"]
        
        # Clean up the question if it's a mention
        user_question = re.sub(f"<@{body['api_app_id']}>", "", user_question).strip()

        if not user_question:
            say("Please ask a question after mentioning me!")
            return

        # Get user's role from their Slack profile
        user_role = get_user_role(user_id, client)
        
        # Get the answer from the GPT service
        answer = gpt_service.get_answer(query=user_question, user_role=user_role)
        
        # Send the final answer
        say(text=answer)
        
    except Exception as e:
        print(f"Error processing request: {e}")
        say("Sorry, I encountered an error while processing your request. Please try again later.")


# --- SLACK EVENT LISTENERS ---

@slack_app.event("app_mention")
def handle_app_mentions(body, say, client, logger):
    """Handles mentions of the bot in any channel."""
    # Acknowledge the request immediately
    say(f"Hello <@{body['user']}>! I'm thinking about your question...")
    
    # Offload the actual processing to a background thread
    thread = Thread(target=process_request, args=(body['event'], say, client))
    thread.start()

@slack_app.command("/ask-metamorphic-gpt")
def handle_slash_command(ack, body, say, client, logger):
    """Handles the /ask-metamorphic-gpt slash command."""
    # Acknowledge the command request immediately
    ack()
    
    # Acknowledge the request immediately
    say(f"Hello <@{body['user_id']}>! I'm thinking about your question...")

    # Offload the actual processing to a background thread
    thread = Thread(target=process_request, args=(body, say, client))
    thread.start()