import os
import logging
import discord
import httpx
import asyncio
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('aossie-bot')

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
DISCORD_CHANNEL_ID_INT = None
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2')
SKILL_FILE_PATH = os.getenv('SKILL_FILE_PATH', '.clinerules')
OLLAMA_URL = "http://localhost:11434/api/generate"

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Lock to prevent Ollama requests from clashing
ollama_lock = asyncio.Lock()

def load_skill_context() -> str:
    """Load context from the local skill file."""
    try:
        if os.path.exists(SKILL_FILE_PATH):
            with open(SKILL_FILE_PATH, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        logger.error(f"Error loading skill file {SKILL_FILE_PATH}: {e}")
    return ""

async def generate_ollama_response(prompt: str, context: str) -> str:
    """Send prompt to local Ollama instance and return the response."""
    if context:
        system_prompt = f"You are a helpful contributor assistant for AOSSIE.\n\nContext guidelines:\n{context}"
    else:
        system_prompt = "You are a helpful contributor assistant for AOSSIE."

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            response = await http_client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "Error: No response text found in Ollama reply.")
    except httpx.TimeoutException:
        logger.error("Ollama request timed out.")
        return "I'm sorry, the local AI model timed out while thinking. Please try again later."
    except httpx.RequestError as e:
        logger.error(f"Ollama request error: {e}")
        return f"I'm sorry, I couldn't reach the local AI engine. Ensure Ollama is running at localhost:11434."
    except Exception as e:
        logger.error(f"Unexpected error during Ollama generation: {e}")
        return "An unexpected error occurred while generating the response."

async def process_message(message: discord.Message):
    """Process a single message and generate a reply safely."""
    if message.author.bot or message.channel.id != DISCORD_CHANNEL_ID_INT:
        return

    # Use lock to ensure only one message is processed by Ollama at a time
    async with ollama_lock:
        async with message.channel.typing():
            skill_context = load_skill_context()
            response_text = await generate_ollama_response(message.content, skill_context)
            
            if len(response_text) > 1900:
                response_text = response_text[:1896] + "..."

            await message.reply(response_text)

async def wait_for_ollama():
    """Wait until Ollama is up and responding."""
    logger.info("Waiting for Ollama to be ready...")
    while True:
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get("http://localhost:11434/")
                if response.status_code == 200:
                    logger.info("Ollama is ready!")
                    return
        except httpx.RequestError:
            pass
        logger.info("Ollama not reachable yet. Retrying in 10 seconds...")
        await asyncio.sleep(10)

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user.name} ({client.user.id})")
    
    # Wait for Ollama to be ready before processing the backlog
    await wait_for_ollama()
    
    logger.info("Checking for missed messages...")
    
    try:
        channel = await client.fetch_channel(DISCORD_CHANNEL_ID_INT)
        
        # Find the last message sent by the bot
        last_bot_msg = None
        async for msg in channel.history(limit=50):
            if msg.author.id == client.user.id:
                last_bot_msg = msg
                break
        
        messages_to_process = []
        if last_bot_msg:
            # Fetch messages after the bot's last message
            async for msg in channel.history(after=last_bot_msg, oldest_first=True):
                if not msg.author.bot:
                    messages_to_process.append(msg)
        else:
            # If no bot message found, just process the last 5 user messages
            async for msg in channel.history(limit=5, oldest_first=True):
                if not msg.author.bot:
                    messages_to_process.append(msg)
                    
        logger.info(f"Found {len(messages_to_process)} missed messages. Processing...")
        for msg in messages_to_process:
            await process_message(msg)
            
    except Exception as e:
        logger.error(f"Error fetching missed messages: {e}")

    logger.info("AOSSIE Contributor Assistant MVP is fully ready.")

@client.event
async def on_message(message: discord.Message):
    await process_message(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is missing from environment. Exiting.")
        exit(1)

    if not DISCORD_CHANNEL_ID:
        logger.critical("DISCORD_CHANNEL_ID is missing from environment. Exiting.")
        exit(1)

    try:
        DISCORD_CHANNEL_ID_INT = int(DISCORD_CHANNEL_ID)
    except ValueError:
        logger.critical(
            f"DISCORD_CHANNEL_ID '{DISCORD_CHANNEL_ID}' is not a valid integer. Exiting."
        )
        exit(1)

    logger.info("Starting bot...")
    client.run(DISCORD_TOKEN)