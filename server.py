from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
import os
from typing import Optional
from dotenv import load_dotenv
import fingerprint_pro_server_api_sdk
from fingerprint_pro_server_api_sdk.rest import ApiException

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
api_key = os.getenv("FINGERPRINT_API_KEY")
if not api_key:
    raise ValueError("FINGERPRINT_API_KEY environment variable is required")

# Initialize Fingerprint client
configuration = fingerprint_pro_server_api_sdk.Configuration(api_key=api_key, region="eu")
client = fingerprint_pro_server_api_sdk.FingerprintApi(configuration)

# Initialize SQLite database
def init_database():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            visitorId TEXT
        )
    """)
    conn.commit()
    conn.close()

# Initialize database on startup
init_database()

app = FastAPI(title="Fingerprint.js Python Backend", version="1.0.0")

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response validation
class CreateAccountRequest(BaseModel):
    requestId: str
    username: str
    password: str

class CreateAccountResponse(BaseModel):
    status: str
    visitorId: str
    botResult: str

class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None
    botResult: Optional[str] = None
    visitorId: Optional[str] = None

@app.post("/api/create-account", response_model=CreateAccountResponse)
async def create_account(request: CreateAccountRequest):
    # Validate required fields
    if not request.requestId:
        raise HTTPException(
            status_code=400,
            detail="Missing requestId. Please provide a valid Fingerprint requestId."
        )

    if not request.username or not request.password:
        raise HTTPException(
            status_code=400,
            detail="Missing username or password."
        )

    try:
        # Get visitor identification details using the requestId
        event = client.get_event(request.requestId)
        
        # Convert event to dictionary for easier access
        event_dict = event.to_dict() if hasattr(event, 'to_dict') else event.__dict__
        
        # Extract visitor ID
        visitor_id = event_dict["products"]["identification"]["data"]["visitorId"]
        
        # Check for bot activity
        bot_result = "unknown"
        bot_detected = False
        
        if "botd" in event_dict["products"] and event_dict["products"]["botd"]["data"]["bot"]["result"]:
            bot_result = event_dict["products"]["botd"]["data"]["bot"]["result"]
            bot_detected = bot_result != "notDetected"

        if bot_detected:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Bot detected. Failed to create account.",
                    "botResult": bot_result
                }
            )

        # Check if this device has already created an account
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT COUNT(*) as count FROM accounts WHERE visitorId = ?",
            (visitor_id,)
        )
        row = cursor.fetchone()
        
        if row[0] > 0:
            conn.close()
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Device already has an account. Failed to create account.",
                    "visitorId": visitor_id
                }
            )

        # Insert the new account
        cursor.execute(
            "INSERT INTO accounts (username, password, visitorId) VALUES (?, ?, ?)",
            (request.username, request.password, visitor_id)
        )
        conn.commit()
        conn.close()

        return CreateAccountResponse(
            status="Account created successfully!",
            visitorId=visitor_id,
            botResult=bot_result
        )

    except HTTPException:
        raise
    except Exception as error:
        print("Fingerprint API error:", str(error))

        # Handle specific Fingerprint API errors
        if "requestId is not set" in str(error):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid requestId. Please ensure you're sending a valid Fingerprint requestId.",
                    "details": "The requestId should be obtained from the Fingerprint front-end SDK"
                }
            )

        if "not found" in str(error):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Request not found. The requestId may be invalid or expired.",
                    "details": str(error)
                }
            )

        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to verify visitor identity",
                "details": str(error)
            }
        )

@app.get("/health")
async def health_check():
    return {"status": "Server is running"}

@app.get("/api/accounts")
async def get_accounts():
    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, visitorId FROM accounts")
        rows = cursor.fetchall()
        conn.close()
        
        accounts = [
            {"id": row[0], "username": row[1], "visitorId": row[2]}
            for row in rows
        ]
        return {"accounts": accounts}
    except Exception as e:
        print("Database error:", str(e))
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

if __name__ == "__main__":
    import uvicorn
    print("Server starting on http://localhost:3000")
    print("Health check: http://localhost:3000/health")
    print("Create account: POST http://localhost:3000/api/create-account")
    print("View accounts: GET http://localhost:3000/api/accounts")
    uvicorn.run(app, host="0.0.0.0", port=3000) 