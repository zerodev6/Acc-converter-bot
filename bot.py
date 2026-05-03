import os
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# CONFIGURATION
# ==========================================
# Fetching from environment variables (Set these in Koyeb)
API_ID = "20288994"
API_HASH = "d702614912f1ad370a0d18786002adbf"
BOT_TOKEN = "8610998423:AAGAneW7hmfW8kUP_FUCXjjb_jl5_BQXUQA"

# Initialize Pyrogram Client
app = Client(
    "converter_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024 # 2GB
SUPPORTED_FORMATS = [
    'eac3', 'ac3', 'dts', 'mp3', 'flac', 'wav', 
    'ogg', 'opus', 'wma', 'aac', 'mkv', 'mp4', 'avi'
]

# In-memory user settings
USER_SETTINGS = {}

def get_user_settings(user_id):
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {'bitrate': '320k', 'ar': '44100', 'ac': '2'}
    return USER_SETTINGS[user_id]

# ==========================================
# COMMAND HANDLERS
# ==========================================

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "👋 Welcome! Send me any audio or video file, and I will convert it to a high-quality AAC M4A format.\n\n"
        "Type /help to see how it works or /settings to change conversion quality."
    )

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    help_text = (
        "🛠 **How to use this bot:**\n"
        "1. Simply upload or forward an audio/video file to me.\n"
        f"2. Supported formats: {', '.join(SUPPORTED_FORMATS).upper()}\n"
        "3. Wait for the download and conversion to finish.\n"
        "4. I will send you back the M4A file!\n\n"
        "Maximum file size: 2GB.\n"
        "Use /settings to adjust bitrate, sample rate, and channels."
    )
    await message.reply_text(help_text)

# ==========================================
# SETTINGS MENU
# ==========================================

def generate_markup(settings):
    ac_label = "Stereo" if settings['ac'] == '2' else "Mono"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Bitrate: {settings['bitrate']}", callback_data="toggle_bitrate")],
        [InlineKeyboardButton(f"Sample Rate: {settings['ar']} Hz", callback_data="toggle_ar")],
        [InlineKeyboardButton(f"Channels: {ac_label}", callback_data="toggle_ac")]
    ])

@app.on_message(filters.command("settings"))
async def settings_cmd(client, message):
    settings = get_user_settings(message.from_user.id)
    await message.reply_text(
        "⚙️ **Conversion Settings**\nChoose your preferred quality:",
        reply_markup=generate_markup(settings)
    )

@app.on_callback_query(filters.regex("^toggle_"))
async def settings_callback(client, callback_query):
    user_id = callback_query.from_user.id
    settings = get_user_settings(user_id)
    action = callback_query.data

    if action == "toggle_bitrate":
        options = ['128k', '192k', '320k']
        settings['bitrate'] = options[(options.index(settings['bitrate']) + 1) % len(options)]
    elif action == "toggle_ar":
        options = ['44100', '48000']
        settings['ar'] = options[(options.index(settings['ar']) + 1) % len(options)]
    elif action == "toggle_ac":
        settings['ac'] = '1' if settings['ac'] == '2' else '2'

    USER_SETTINGS[user_id] = settings
    await callback_query.message.edit_reply_markup(generate_markup(settings))
    await callback_query.answer()

# ==========================================
# FILE HANDLING & CONVERSION
# ==========================================

@app.on_message(filters.audio | filters.video | filters.document)
async def handle_files(client, message):
    # Determine file object and extension
    file_obj = message.audio or message.video or message.document
    file_name = getattr(file_obj, "file_name", "unknown_file")
    file_size = getattr(file_obj, "file_size", 0)

    ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
    
    if ext not in SUPPORTED_FORMATS:
        await message.reply_text("❌ Error: Unsupported format. Please send a valid audio or video file.")
        return

    if file_size > MAX_FILE_SIZE:
        await message.reply_text("❌ Error: File too large (max 2GB).")
        return

    status_msg = await message.reply_text("📥 Downloading your file...")

    # Define paths
    input_path = f"input_{file_obj.file_id}.{ext}"
    output_path = f"output_{file_obj.file_id}.m4a"

    try:
        # 1. Download File
        await message.download(file_name=input_path)

        # 2. Convert File (Async Subprocess)
        await status_msg.edit_text("🔄 Converting to AAC M4A...")
        settings = get_user_settings(message.from_user.id)
        
        command = [
            'ffmpeg', '-y', 
            '-i', input_path, 
            '-c:a', 'aac', 
            '-b:a', settings['bitrate'], 
            '-ac', settings['ac'], 
            '-ar', settings['ar'], 
            '-vn', output_path
        ]
        
        # Run FFmpeg asynchronously so it doesn't block the bot
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()

        if process.returncode != 0:
            raise Exception("FFmpeg process failed.")

        # 3. Upload File
        await status_msg.edit_text("⬆️ Uploading converted file...")
        new_file_name = f"{os.path.splitext(file_name)[0]}.m4a"
        
        await message.reply_audio(
            audio=output_path,
            title=new_file_name,
            caption="✅ Converted successfully!"
        )
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error during processing: {str(e)}")
    
    finally:
        # 4. Clean up temporary files
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)

# ==========================================
# BOT START
# ==========================================

if __name__ == '__main__':
    print("Bot is starting...")
    app.run()

