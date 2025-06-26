# Fingerprint.js Python Backend Quickstart

This quickstart guide shows you how to build a Python backend that uses Fingerprint.js to prevent fraudulent account creation. You'll learn how to:

- Set up a FastAPI server with Fingerprint.js integration
- Retrieve visitor identification data using the Server API
- Block bots and suspicious devices
- Prevent multiple signups from the same device

## Prerequisites

Before you begin, make sure you have the following:

- [Python](https://www.python.org/) (3.8 or later) installed
- Your favorite code editor
- Basic knowledge of Python
- An existing front‑end implementation that sends a `requestId`

> \*Note: This quickstart only covers the back-end setup. You'll first need a front-end integration to send the `requestId` to your server. **Links to front-end quickstarts are on the main quickstart page and at the end of this guide.\***

## 1. Get your secret API key

Before starting this quickstart, you should already have a front-end Fingerprint implementation that sends the `requestId` to your server. **If not, pause here and check out one of our front-end or mobile quickstarts first.**

If you're ready:

1. Sign in and go to the [**API keys**](https://dashboard.fingerprint.com/api-keys) page in the Fingerprint dashboard.
2. Create a new **secret API key**.
3. Copy it somewhere safe so you can use it to retrieve full visitor identification data from the Server API.

## 2. Set up your project

To get started, set up a basic server. If you already have a project you want to use, you can skip to the next section.

1. Create a new Python project and set up the virtual environment:

```bash
mkdir fingerprint-python-starter && cd fingerprint-python-starter
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies from the requirements.txt file:

```bash
pip install -r requirements.txt
```

_Note: This quickstart is written for SDK version 8.x_

3. Create a new file called `server.py` and add a basic FastAPI server setup:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/create-account")
async def create_account():
    # We'll add Fingerprint logic here
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
```

## 3. Initialize Fingerprint and retrieve visitor data

Now you'll configure the Fingerprint server SDK using your secret API key and use it to fetch detailed visitor data for each signup attempt.

When making the initial visitor identification request in the front end, you received a `requestId`. This ID is unique to each identification event. Your server can then use the [Fingerprint Events API](https://dev.fingerprint.com/reference/server-api-get-event) and retrieve the complete identification data, including the trusted visitor ID and other actionable insights like whether they are using a VPN or are a bot.

1. At the top of your `server.py` file, import and initialize the SDK:

```python
import os
from dotenv import load_dotenv
import fingerprint_pro_server_api_sdk
from fingerprint_pro_server_api_sdk.rest import ApiException

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
api_key = os.getenv("FINGERPRINT_API_KEY")
if not api_key:
    raise ValueError("FINGERPRINT_API_KEY environment variable is required")

# Initialize Fingerprint client with your Fingerprint.js subscription region
# Available regions: "us" (default), "eu", "ap"
# You can find your region in the Fingerprint dashboard under your API keys
configuration = fingerprint_pro_server_api_sdk.Configuration(api_key=api_key, region="eu")
client = fingerprint_pro_server_api_sdk.FingerprintApi(configuration)
```

2. Create a `.env` file in your project root and add your API key:

```env
FINGERPRINT_API_KEY=your-secret-api-key-here
```

3. In your `/api/create-account` route, use the `requestId` you are sending from the front end to fetch the full visitor identification details:

```python
from pydantic import BaseModel

class CreateAccountRequest(BaseModel):
    requestId: str
    username: str
    password: str

@app.post("/api/create-account")
async def create_account(request: CreateAccountRequest):
    # Get the full visitor identification details using the requestId
    event = client.get_event(request.requestId)

    # ...
```

The event object contains the visitor ID, IP address, device and browser details, and Smart Signals like bot detection, incognito mode, and whether the user is on a VPN or virtual machine.

You can see a full example of the event structure, and test it with your own device, in our [demo playground](https://demo.fingerprint.com/playground).

## 4. Block bots and suspicious devices

A simple but powerful way to prevent fraudulent account creation is to block automated signups that come from bots. The `event` object includes the Bot Detection Smart Signal that flags automated activity, making it easy to reject bot traffic.

1. In your `/api/create-account` route, check the bot signal returned in the event object:

```python
    # Check for bot activity (only if bot detection data is available)
    bot_detected = False
    bot_result = "unknown"

    try:
        if (
            "botd" in event_dict["products"] and
            event_dict["products"]["botd"] and
            event_dict["products"]["botd"]["data"] and
            "bot" in event_dict["products"]["botd"]["data"]
        ):
            bot_result = event_dict["products"]["botd"]["data"]["bot"]["result"]
            bot_detected = bot_result != "notDetected"
    except (KeyError, TypeError):
        print("Bot detection data not available in response")

    if bot_detected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Bot detected. Failed to create account.",
                "botResult": bot_result
            }
        )
```

This signal returns `good` for known bots like search engines, `bad` for automation tools, headless browsers, or other signs of automation, and `notDetected` when no bot activity is found. You can also layer in other Smart Signals to catch more suspicious devices. For example, you can use Fingerprint's [Suspect Score](https://dev.fingerprint.com/docs/suspect-score) to determine when to add additional friction to create an account.

## 5. Prevent multiple signups from the same device

To catch repeated signups from the same device, you can use the `visitorId` from the Fingerprint identification event. By saving this ID alongside each created account, you can easily detect and block duplicate signups. We'll be using a simple database to demonstrate how this works with SQLite.

1. At the top of your `server.py` file, import and initialize the database:

```python
import sqlite3

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
```

2. In your `/api/create-account` route handler, after getting the event, extract the `visitorId`:

```python
    # Extract visitor ID
    try:
        visitor_id = event_dict["products"]["identification"]["data"]["visitorId"]
    except (KeyError, TypeError):
        # Try accessing as object attributes
        visitor_id = event.products.identification.data.visitor_id
```

3. Check if this device has already created an account; if yes, block the account creation:

```python
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

    # Otherwise, insert the new account
    cursor.execute(
        "INSERT INTO accounts (username, password, visitorId) VALUES (?, ?, ?)",
        (request.username, request.password, visitor_id)
    )
    conn.commit()
    conn.close()
```

This gives you a basic system to detect and block repeat signups. You can expand on this by allowing a limited number of accounts per device, adjusting your response based on business rules, only evaluating recent signups, etc.

> Note: This is a minimal example to show how to use the Fingerprint SDK. In a real application, make sure to implement proper security practices, especially around password handling and storage.

## 6. Test your implementation

Now that everything is set up, you can test the full flow using your existing front end.

### Before you test

If your front end is running on a different port (like localhost:5173 or localhost:3001), you may run into CORS issues for testing. The CORS middleware is already configured in the setup above for local development & testing.

### Test the implementation

1. Start your FastAPI server:

```bash
python server.py
```

2. In your front end, trigger a sign-up request that sends the `requestId`, `username`, and `password` to your `/api/create-account` endpoint.
3. Test the intended behavior and confirm that if the same device tries to create multiple accounts, the second attempt should be rejected.
4. Bonus: Try creating an account using a headless browser.

## Additional endpoints

The implementation includes several additional endpoints for testing and monitoring:

- **Health check**: `GET /health` - Returns server status
- **View accounts**: `GET /api/accounts` - Lists all created accounts (for testing purposes)

## API Reference

### POST /api/create-account

Creates a new account with fraud detection.

**Request Body:**

```json
{
  "requestId": "string",
  "username": "string",
  "password": "string"
}
```

**Example request:**

```bash
curl -X POST http://localhost:3000/api/create-account \
  -H "Content-Type: application/json" \
  -d '{
    "requestId": "example-request-id-12345",
    "username": "test@example.com",
    "password": "password123"
  }'
```

**Note:** Replace the requestId with a valid Fingerprint requestId from your front-end implementation. The example requestId above is just a placeholder and won't work without a real Fingerprint identification event

**Response:**

- `200`: Account created successfully
- `400`: Missing or invalid requestId
- `403`: Bot detected
- `429`: Device already has an account
- `500`: Server error

### GET /health

Returns server health status.

```bash
curl http://localhost:3000/health
```

### GET /api/accounts

Returns all created accounts (for testing purposes).

```bash
curl http://localhost:3000/api/accounts
```

## Troubleshooting

### Common issues:

1. **Import errors**: Make sure you've installed all dependencies from `requirements.txt`
2. **API key errors**: Ensure your `.env` file contains the correct `FINGERPRINT_API_KEY`
3. **CORS issues**: The CORS middleware is configured for local development. In production, specify your frontend domain
4. **Database errors**: Ensure the `database.db` file is writable in your project directory

### Debug mode:

The server includes extensive logging to help debug issues. Check the console output for detailed information about each request.

## Get the code

You can find the complete code for this quickstart in the GitHub repository:

**[https://github.com/sedyldz/fingerprint-python-starter](https://github.com/sedyldz/fingerprint-python-starter)**

To get started quickly:

```bash
git clone <https://github.com/sedyldz/fingerprint-python-starter>
cd fingerprint-python-starter
```

The repository contains:

- Complete FastAPI server implementation
- All required dependencies in `requirements.txt`
- Environment configuration with `.env.example`
- Simple error handling and logging
- Additional testing endpoints

## Next steps

You now have a working back-end fraud check using Fingerprint. From here, you can expand your logic with more Smart Signals, adjust thresholds based on your risk tolerance, or introduce additional checks for suspicious users.

These same techniques apply to a wide range of fraud prevention use cases, from detecting fake reviews to blocking payment abuse or preventing account takeovers.

To go further, check out our **use case tutorials** for step-by-step guides tailored to specific problems you can solve with Fingerprint.

Check out these related resources:

- [Python SDK Reference](https://github.com/fingerprintjs/fingerprintjs-pro-server-api-python-sdk)
- **Vue front end quickstart**
- [API reference for the Events endpoint](https://dev.fingerprint.com/reference/server-api-get-event)
- **Use case tutorial: Detecting new account fraud**
- [Low-latency identification with Sealed Client Results](https://dev.fingerprint.com/docs/sealed-client-results)
