import asyncio
import json
import logging
import websockets
import aiofiles
from aiohttp import web
import os

# --- Basic Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
PUMP_PORTAL_WEBSOCKET_URL = "wss://pumpportal.fun/api/data"
LOG_FILE = "pumpportal_log.json"

# --- Helper function to log raw data to a file ---
async def log_to_json_file(raw_message: str):
    """Appends the raw JSON string to the log file."""
    try:
        async with aiofiles.open(LOG_FILE, mode="a", encoding="utf-8") as f:
            await f.write(raw_message + "\n")
    except Exception as e:
        logger.error(f"❌ Failed to write to log file: {e}")

# --- WebSocket Broadcasting Logic ---
async def broadcast_to_clients(app: web.Application, message: str):
    """Sends a message to all connected frontend clients."""
    for ws in app['websockets']:
        try:
            await ws.send_str(message)
        except ConnectionResetError:
            logger.warning("Client connection was reset.")
        except Exception as e:
            logger.error(f"Error sending to client: {e}")

# --- External WebSocket Listener ---
async def pump_portal_listener(app: web.Application):
    """Connects to Pump Portal and forwards the raw data stream."""
    while True:
        try:
            async with websockets.connect(PUMP_PORTAL_WEBSOCKET_URL) as ws:
                logger.info("✅ Successfully connected to Pump Portal WebSocket.")
                
                subscribe_payload = {"method": "subscribeNewToken"}
                await ws.send(json.dumps(subscribe_payload))
                logger.info("✅ Subscribed to 'subscribeNewToken' stream.")
                
                async for message in ws:
                    logger.info(f"⬇️ Received message from Pump Portal.")
                    
                    if isinstance(message, (bytes, bytearray)):
                        decoded_message = message.decode("utf-8")
                    else:
                        decoded_message = str(message)

                    await log_to_json_file(decoded_message)
                    await broadcast_to_clients(app, decoded_message)
        except Exception as e:
            logger.error(f"❌ Pump Portal connection error: {e}")
            await asyncio.sleep(10)

# --- HTTP and WebSocket Handlers for aiohttp ---

async def handle_http(request):
    """Serves the HTML page to display an unlimited, ordered list of JSON."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Token Feed</title>
        <style>
            body { font-family: monospace; background-color: #121212; color: #e0e0e0; }
            pre { white-space: pre-wrap; word-wrap: break-word; background-color: #1e1e1e; padding: 10px; margin: 0; border-radius: 4px; }
            hr { border: 1px solid #444; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div id="output"></div>
        <script>
            const output = document.getElementById('output');
            let messages = []; // Array to store all incoming messages

            const ws = new WebSocket(`ws://${window.location.host}/ws`);

            ws.onmessage = (event) => {
                try {
                    const newMessage = JSON.parse(event.data);

                    // Add the new message to the beginning of the array
                    messages.unshift(newMessage);

                    // Regenerate the HTML for all messages
                    output.innerHTML = messages.map(msg => {
                        return `<pre>${JSON.stringify(msg, null, 2)}</pre>`;
                    }).join('<hr>'); // Separate entries with a horizontal line

                } catch (e) {
                    console.error('Error parsing JSON:', e);
                }
            };
        </script>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')

async def handle_websocket(request):
    """Handles WebSocket connections from the browser."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    logger.info("✅ Frontend client connected.")
    request.app['websockets'].add(ws)
    
    try:
        async for msg in ws:
            pass
    finally:
        logger.info("❌ Frontend client disconnected.")
        request.app['websockets'].remove(ws)
        
    return ws

# --- Application Startup ---

async def on_startup(app: web.Application):
    """Actions to perform on server startup."""
    asyncio.create_task(pump_portal_listener(app))
    with open(LOG_FILE, "w") as f:
        f.write("")

if __name__ == "__main__":
    app = web.Application()
    app['websockets'] = set()

    app.router.add_get("/", handle_http)
    app.router.add_get("/ws", handle_websocket)
    app.on_startup.append(on_startup)

    logger.info("🚀 Starting server on http://localhost:0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    web.run_app(app, host="0.0.0.0", port=port)