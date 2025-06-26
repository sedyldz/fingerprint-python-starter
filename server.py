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

app = FastAPI(title="Fingerprint Python Backend", version="1.0.0")

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

@app.post("/api/create-account", response_model=CreateAccountResponse)
async def create_account(request: CreateAccountRequest):
    # Get visitor identification details using the requestId
    event = client.get_event(request.requestId)
    
    # Convert event to dictionary for easier access
    event_dict = event.to_dict() if hasattr(event, 'to_dict') else event.__dict__

    # Extract visitor ID
    visitor_id = event_dict["products"]["identification"]["data"]["visitor_id"]
    
    # Check for bot activity
    bot_result = "unknown"
    if "botd" in event_dict["products"] and event_dict["products"]["botd"]["data"]["bot"]["result"] == "detected":
        raise HTTPException(status_code=403, detail="Bot detected")

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
        raise HTTPException(status_code=429, detail="Device already has an account")

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

@app.get("/health")
async def health_check():
    return {"status": "Server is running"}

@app.get("/api/accounts")
async def get_accounts():
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

if __name__ == "__main__":
    import uvicorn
    print("Server starting on http://localhost:3001")
    print("Health check: http://localhost:3001/health")
    print("Create account: POST http://localhost:3001/api/create-account")
    print("View accounts: GET http://localhost:3001/api/accounts")
    uvicorn.run(app, host="0.0.0.0", port=3001) 