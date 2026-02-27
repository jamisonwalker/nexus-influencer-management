# listener.py
import os
import hmac
import hashlib
import time
import requests
import uvicorn
import logging
import yaml
import re
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from typing import Dict, Any

# Import Sarah's brain logic
from brain import generate_sarah_response

# Import Fanvue OAuth integration
from fanvue import FanvueOAuth

# Load configuration from config.yaml
with open(os.path.join(os.path.dirname(__file__), "config.yaml"), "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI(title="Sarah-Engine", version="1.0.0")

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "Sarah-Engine is running"}

@app.get("/auth/login")
async def login():
    """
    Initiates the Fanvue OAuth flow by generating PKCE parameters and redirecting to Fanvue
    """
    try:
        # Generate PKCE parameters
        pkce = fanvue_oauth.generate_pkce_parameters()
        
        # Store code verifier in cookie (httponly and secure for production)
        auth_url = fanvue_oauth.get_authorization_url(pkce['code_challenge'])
        
        logger.info("OAuth flow initiated")
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error(f"❌ Failed to initiate OAuth flow: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to initiate login")

@app.get("/auth/callback")
async def callback(code: str, state: str):
    """
    OAuth callback endpoint to exchange authorization code for tokens
    """
    try:
        logger.info(f"Received OAuth callback with code: {code[:10]}...")
        
        # NOTE: In a real implementation, you would retrieve the code_verifier from cookies or session
        # For this example, we're generating a new one (this won't work in production)
        # You should implement proper session management
        
        logger.warning("⚠️  Code verifier not properly stored in session - this is a demo implementation")
        
        # This is just for demonstration - in production, you need to store and retrieve
        # the code_verifier that was generated during the login step
        pkce = fanvue_oauth.generate_pkce_parameters()
        
        try:
            tokens = fanvue_oauth.exchange_code_for_tokens(code, pkce['code_verifier'])
            logger.info("✅ OAuth token exchange successful")
            
            # Store tokens in token cache
            token_cache["token"] = tokens["access_token"]
            token_cache["expires_at"] = time.time() + tokens.get("expires_in", 3600) - 300
            
            # Get user profile
            user_profile = fanvue_oauth.get_user_profile(tokens["access_token"])
            
            return {
                "status": "success",
                "message": "Login successful",
                "user": user_profile,
                "tokens": {
                    "access_token": tokens["access_token"],
                    "expires_in": tokens["expires_in"],
                    "refresh_token": tokens.get("refresh_token")
                }
            }
        except Exception as e:
            logger.error(f"❌ Token exchange failed: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")
            
    except Exception as e:
        logger.error(f"❌ OAuth callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.get("/auth/refresh")
async def refresh(refresh_token: str):
    """
    Refresh access token using refresh token
    """
    try:
        logger.info("🔄 Refreshing access token")
        new_tokens = fanvue_oauth.refresh_access_token(refresh_token)
        
        token_cache["token"] = new_tokens["access_token"]
        token_cache["expires_at"] = time.time() + new_tokens.get("expires_in", 3600) - 300
        
        logger.info("✅ Access token refreshed successfully")
        return {
            "status": "success",
            "tokens": {
                "access_token": new_tokens["access_token"],
                "expires_in": new_tokens["expires_in"],
                "refresh_token": new_tokens.get("refresh_token")
            }
        }
    except Exception as e:
        logger.error(f"❌ Token refresh failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Failed to refresh token")

# --- Configurations ---
SIGNING_SECRET = os.getenv("FANVUE_WEBHOOK_SECRET")
CLIENT_ID = os.getenv("FANVUE_CLIENT_ID")
CLIENT_SECRET = os.getenv("FANVUE_CLIENT_SECRET")
API_VERSION = os.getenv("FANVUE_API_VERSION", "2025-06-26")

# PostgreSQL Connection Setup using psycopg2
def get_db_connection():
    """Get a connection to the PostgreSQL database"""
    try:
        conn = psycopg2.connect(os.getenv("SUPABASE_DB_URL"))
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        raise

# Initialize Fanvue OAuth client
fanvue_oauth = FanvueOAuth()

# Token Cache to prevent unnecessary auth requests
token_cache = {"token": None, "expires_at": 0}

def get_fanvue_token() -> str:
    """Refreshes OAuth token only when expired (approx every 24h)"""
    if token_cache["token"] and time.time() < token_cache["expires_at"]:
        return token_cache["token"]

    logger.info("🔑 Refreshing Fanvue OAuth Token...")
    try:
        # NOTE: The current implementation uses client_credentials flow,
        # but the Fanvue documentation recommends authorization code flow with PKCE
        # for user authentication. This is kept for backward compatibility.
        resp = requests.post(
            "https://api.fanvue.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": "chat:read chat:write"
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        token_cache["token"] = data["access_token"]
        token_cache["expires_at"] = time.time() + data.get("expires_in", 86400) - 300
        logger.info("✅ OAuth token refreshed successfully")
        return token_cache["token"]
    except Exception as e:
        logger.error(f"❌ Failed to refresh OAuth token: {str(e)}")
        raise

def verify_signature(payload: str, signature_header: str) -> bool:
    """Verifies Svix-style signatures from Fanvue"""
    try:
        # Expected format: t=123,v0=abc
        parts = dict(x.split('=') for x in signature_header.split(','))
        timestamp, received_sig = parts.get('t'), parts.get('v0')
        
        if not timestamp or not received_sig or abs(time.time() - int(timestamp)) > 300:
            logger.warning("❌ Signature verification failed: Invalid timestamp or signature")
            return False

        to_sign = f"{timestamp}.{payload}".encode()
        expected_sig = hmac.new(SIGNING_SECRET.encode(), to_sign, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(expected_sig, received_sig):
            logger.warning("❌ Signature verification failed: Mismatch")
            return False
            
        logger.info("✅ Signature verified successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Signature verification error: {str(e)}")
        return False

async def update_fan_lore(fan_id: str, incoming_text: str, fan_name: str, previous_lore: str = "") -> str:
    """
    Use AI to determine what fan information should be updated
    
    Args:
        fan_id: Fan's unique identifier
        incoming_text: Current message from fan
        fan_name: Fan's name or nickname
        previous_lore: Existing fan lore
        
    Returns:
        Updated fan lore string
    """
    # Import the AI lore generation function
    from brain import generate_lore_update
    
    # Use AI to analyze the message for new lore
    new_info = generate_lore_update(incoming_text, previous_lore)
    
    if new_info == "NO_NEW_INFO":
        return previous_lore.strip()
    
    # Add new information to the lore
    if previous_lore:
        updated_lore = f"{previous_lore}\n{new_info}"
    else:
        updated_lore = new_info
    
    return updated_lore.strip()

async def process_message(data: Dict[str, Any]):
    """Process incoming message from Fanvue"""
    try:
        # Extract data from the event (handle different data structures)
        event_data = data.get('data', data)
        
        fan_id = event_data.get('sender', {}).get('uuid') or event_data.get('userId')
        incoming_text = event_data.get('message', {}).get('text') or event_data.get('text')
        msg_id = event_data.get('message', {}).get('uuid') or event_data.get('id')
        chat_id = event_data.get('chat', {}).get('uuid') or event_data.get('chatId')
        
        # Log the event data for debugging
        logger.info(f"Event data: {data}")

        logger.info(f"Processing message from fan {fan_id}: {incoming_text[:50]}...")

        # Get database connection
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 1. Ensure fan_lore record exists first (to satisfy foreign key constraint)
        cur.execute("SELECT * FROM fan_lore WHERE fan_id = %s", (fan_id,))
        lore = cur.fetchone()
        
        if not lore:
            # Create new fan lore record if not exists
            logger.info(f"Creating new fan lore record for fan {fan_id}")
            cur.execute("""
                INSERT INTO fan_lore (fan_id, name, lore_text, last_vibe)
                VALUES (%s, %s, %s, %s)
            """, (fan_id, "Unknown", "", "Friendly"))
            conn.commit()
            cur.execute("SELECT * FROM fan_lore WHERE fan_id = %s", (fan_id,))
            lore = cur.fetchone()

        # 2. Save the new message to PostgreSQL immediately (User)
        cur.execute("""
            INSERT INTO messages (id, fan_id, role, content)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (msg_id, fan_id, "user", incoming_text))
        conn.commit()
        logger.info("✅ User message saved to database")

        # 3. Pull History (Last 5 messages)
        
        # Get chat history
        cur.execute("""
            SELECT role, content FROM messages 
            WHERE fan_id = %s 
            ORDER BY created_at DESC LIMIT 6
        """, (fan_id,))
        history = cur.fetchall()
        
        # Reverse history to get chronological order for Aion-2.0
        chat_history = [{"role": row["role"], "content": row["content"]} for row in reversed(history)]
        logger.info(f"✅ Retrieved fan lore and {len(chat_history)} messages")

        # 3. Extract and update fan lore from incoming message
        fan_name = ""
        if lore and "Fan Name:" in lore.get('lore_text', ""):
            fan_name = re.search(r"Fan Name: ([^\n]+)", lore.get('lore_text', "")).group(1)
        
        updated_lore = await update_fan_lore(fan_id, incoming_text, fan_name, lore.get('lore_text', ""))
        
        if updated_lore != lore.get('lore_text', ""):
            cur.execute("""
                UPDATE fan_lore 
                SET lore_text = %s 
                WHERE fan_id = %s
            """, (updated_lore, fan_id))
            conn.commit()
            logger.info("✅ Fan lore updated")
        
        # Extract and update fan name in separate column if available
        name_match = re.search(r"Fan Name: ([^\n]+)", updated_lore)
        if name_match:
            extracted_name = name_match.group(1).strip()
            if extracted_name and extracted_name != "Unknown" and extracted_name != lore.get('name', ""):
                cur.execute("""
                    UPDATE fan_lore 
                    SET name = %s 
                    WHERE fan_id = %s
                """, (extracted_name, fan_id))
                conn.commit()
                logger.info(f"✅ Fan name updated to: {extracted_name}")

        # 4. Generate response with Aion-2.0
        reply_text = generate_sarah_response(
            incoming_text, 
            fan_lore=updated_lore,
            chat_history=chat_history
        )
        logger.info(f"✅ Generated response: {reply_text[:50]}...")

        # 5. Save Sarah's response (Assistant)
        # Generate a unique ID for the assistant message
        import uuid
        assistant_msg_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO messages (id, fan_id, role, content)
            VALUES (%s, %s, %s, %s)
        """, (assistant_msg_id, fan_id, "assistant", reply_text))
        conn.commit()
        logger.info("✅ Assistant response saved to database")

        # 5. Send to Fanvue
        token = get_fanvue_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Fanvue-API-Version": API_VERSION,
            "X-Fanvue-API-Key": os.getenv("FANVUE_API_KEY"),  # Required in 2026
            "Content-Type": "application/json"
        }
        
        resp = requests.post(
            f"https://api.fanvue.com/chats/{chat_id}/messages",
            headers=headers,
            json={"text": reply_text},
            timeout=30
        )
        
        if resp.status_code == 201:
            logger.info("✅ Response sent to Fanvue successfully")
        else:
            logger.error(f"❌ Failed to reply: {resp.status_code} - {resp.text}")
            
    except Exception as e:
        logger.error(f"❌ Error processing message: {str(e)}")
        if 'conn' in locals():
            try:
                conn.rollback()
            except:
                pass
    finally:
        if 'conn' in locals() and conn:
            try:
                conn.close()
            except:
                pass

@app.post("/webhooks/fanvue")
async def fanvue_webhook(request: Request, background_tasks: BackgroundTasks):
    """Fanvue webhook endpoint for incoming messages"""
    signature = request.headers.get("X-Fanvue-Signature")
    body = await request.body()
    payload_str = body.decode()

    if not signature or not verify_signature(payload_str, signature):
        raise HTTPException(status_code=401, detail="Signature mismatch")

    event_data = await request.json()
    
    # Only process actual message events
    if event_data.get("type") in ["message.received", "message.created", "message.recieved"]:
        logger.info(f"Received message event: {event_data.get('id')}")
        background_tasks.add_task(process_message, event_data)
    
    return {"status": "ok"}

if __name__ == "__main__":
    persona = config.get("persona", {})
    hobbies = config.get("hobbies", [])
    logger.info("🚀 Starting Sarah-Engine...")
    logger.info(f"Persona: {persona.get('name', 'Sarah')}, {persona.get('age', 24)} from {persona.get('city', 'Miami')}")
    logger.info(f"Hobbies: {', '.join(hobbies)}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
