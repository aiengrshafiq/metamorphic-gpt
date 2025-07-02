# app/main.py

from fastapi import FastAPI
from app.api.endpoints import router as api_router

# Create the FastAPI application instance
app = FastAPI(
    title="Metamorphic GPT API",
    description="An AI assistant for Metamorphic LLC employees.",
    version="1.0.0"
)

# Include the API router
app.include_router(api_router)

@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Simple health check endpoint to confirm the service is running."""
    return {"status": "ok"}