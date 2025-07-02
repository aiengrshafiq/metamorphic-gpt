# app/core/config.py

import os
from dotenv import load_dotenv

# Load environment variables from the .env file in the root directory
load_dotenv()

class Settings:
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    
    # Slack
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET: str = os.getenv("SLACK_SIGNING_SECRET")
    
    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME")
    
    # Metamorphic GPT
    METAMORPHIC_CORE_VALUES: str = os.getenv("METAMORPHIC_CORE_VALUES")

# Instantiate settings to be imported by other modules
settings = Settings()