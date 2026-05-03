import os
import asyncio
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# CONFIGURATION
# ==========================================
API_ID = "20288994"
API_HASH = "d702614912f1ad370a0d18786002adbf"
BOT_TOKEN = "8610998423:AAGAneW7hmfW8kUP_FUCXjjb_jl5_BQXUQA"

app = Client(
    "converter_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
SUPPORTED_FORMATS = [
    'eac3', 'ac3', 'dts', 'mp3', 'flac', 'wav',
    'ogg', 'opus', 'wma', 'aac', 'mkv', 'mp4', 'avi'
]

USER_SETTINGS = {}

# ==========================================
# RENDER HEALTH CHECK SERVER
# ==========================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"✅ Health server running on port {port}")
    server.serve_forever()

# ==========================================
# PROGRESS BAR
# ==========================================
def make_progress_bar(current, total):
    percent = int((current / total) * 100) if total else 0
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    size_done = round(current / (1024 * 1024), 1)
    size_total = round(total / (1024 * 1024), 1)
    return f"[{bar}] {percent}%\n📦 {size_done} MB / {size_total} MB"

last_update_time = {}

async def progress(current, total, message, action):
    user_id = message.id
    now = time.time()
    if user_id not in last_update_time:
        last_update_time[user_id] = 0
    if now - last_update_time[user_id] < 2:
        return
    last_update_time[user_id] = now
    bar = make_progress_bar(current, total)
    try:
        await message.edit_text(f"{action}\n{bar}")
    except:
        pass

# ==========================================
# SETTINGS
# ==========================================
def get_user_settings(user_id):
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {
            'bitrate': '320k',
            'ar': '48000',
            'ac': '2'
        }
    return USER_SETTINGS[user_id]

def generate_markup(settings):
    ac_label = "Stereo" if settings['ac'] == '2' else "Mono"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🎵 Bitrate: {settings['bitrate']}",
            callback_data="toggle_bitrate")],
        [InlineKeyboardButton(
            f"🎚 Sample Rate: {settings['ar']} Hz",
            callback_data="toggle_ar")],
        [InlineKeyboardButton(
            f"🔊 Channels: {ac_label}",
            callback_data="toggle_ac")]
    ])

# ==========================================
# COMMANDS
# ==========================================
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "👋 **Welcome to Audio Converter Bot!**\n\n"
        "🎵 Send any audio or video file\n"
        "⚡ Fast download + conversion\n"
        "📤 Get M4A back instantly\n\n"
        "📌 /help — How to use\n"
        "⚙️ /settings — Change quality"
    )

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "🛠 **How to use:**\n\n"
        "1️⃣ Send or forward any audio/video file\n"
        f"2️⃣ Supported: {', '.join(SUPPORTED_FORMATS).upper()}\n"
        "3️⃣ Watch the progress bar\n"
        "4️⃣ Get your M4A file!\n\n"
        "📦 Max file size: **2GB**\n"
        "✅ 5.1 Surround → Clear Stereo fix included\n"
        "⚙️ Use /settings to adjust quality"
    )

@app.on_message(filters.command("settings"))
async def settings_cmd(client, message):
    settings = get_user_settings(message.from_user.id)
    await message.reply_text(
        "⚙️ **Conversion Settings**\nTap to change:",
        reply_markup=generate_markup(settings)
    )

@app.on_callback_query(filters.regex("^toggle_"))
async def settings_callback(client, callback_query):
    user_id = callback_query.from_user.id
    settings = get_user_settings(user_id)
    action = callback_query.data

    if action == "toggle_bitrate":
        options = ['128k', '192k', '320k']
        settings['bitrate'] = options[
            (options.index(settings['bitrate']) + 1) % len(options)]
    elif action == "toggle_ar":
        options = ['44100', '48000']
        settings['ar'] = options[
            (options.index(settings['ar']) + 1) % len(options)]
    elif action == "toggle_ac":
        settings['ac'] = '1' if settings['ac'] == '2' else '2'

    USER_SETTINGS[user_id] = settings
    await callback_query.message.edit_reply_markup(
        generate_markup(settings))
    await callback_query.answer("✅ Setting updated!")

# ==========================================
# FILE HANDLING
# ==========================================
@app.on_message(filters.audio | filters.video | filters.document)
async def handle_files(client, message):
    file_obj = message.audio or message.video or message.document
    file_name = getattr(file_obj, "file_name", "unknown_file")
    file_size = getattr(file_obj, "file_size", 0)
    ext = file_name.split('.')[-1].lower() if '.' in file_name else ''

    if ext not in SUPPORTED_FORMATS:
        await message.reply_text(
            "❌ **Unsupported format!**\n"
            f"✅ Supported: {', '.join(SUPPORTED_FORMATS).upper()}"
        )
        return

    if file_size > MAX_FILE_SIZE:
        await message.reply_text(
            "❌ File too large! Max size is **2GB**.")
        return

    size_mb = round(file_size / (1024 * 1024), 1)
    status_msg = await message.reply_text(
        f"📥 **Downloading...**\n"
        f"📦 File size: {size_mb} MB\n"
        f"[░░░░░░░░░░] 0%"
    )

    # ✅ FIXED - Use message.id for clean file path
    safe_id = str(message.id)
    input_path = f"/tmp/input_{safe_id}.{ext}"
    output_path = f"/tmp/output_{safe_id}.m4a"
    start_time = time.time()

    try:
        # ==========================================
        # 1. DOWNLOAD WITH PROGRESS
        # ==========================================
        await message.download(
            file_name=input_path,
            progress=progress,
            progress_args=(status_msg, "📥 **Downloading...**")
        )

        dl_time = round(time.time() - start_time, 1)
        await status_msg.edit_text(
            f"✅ Downloaded in {dl_time}s\n"
            f"🔄 **Converting to AAC M4A...**\n"
            f"[██████████] Please wait..."
        )

        # ==========================================
        # 2. FFMPEG CONVERT
        # ==========================================
        settings = get_user_settings(message.from_user.id)

        command = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-threads', '4',
            '-c:a', 'aac',
            '-b:a', settings['bitrate'],
            '-ac', '2',
            # ✅ 5.1 Surround voice fix
            '-af', 'pan=stereo|FL=FC+0.707*FL+0.707*BL|FR=FC+0.707*FR+0.707*BR',
            '-ar', settings['ar'],
            '-vn',
            '-movflags', '+faststart',
            output_path
        ]

        conv_start = time.time()

        # Capture FFmpeg errors for debugging
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode()[-500:]
            await status_msg.edit_text(
                f"❌ **FFmpeg Error:**\n"
                f"`{error_msg}`\n\n"
                "Please try again."
            )
            return

        conv_time = round(time.time() - conv_start, 1)
        out_size = round(
            os.path.getsize(output_path) / (1024 * 1024), 1)

        await status_msg.edit_text(
            f"✅ Converted in {conv_time}s\n"
            f"📦 Output: {out_size} MB\n"
            f"⬆️ **Uploading...**\n"
            f"[░░░░░░░░░░] 0%"
        )

        # ==========================================
        # 3. UPLOAD WITH PROGRESS
        # ==========================================
        new_file_name = f"{os.path.splitext(file_name)[0]}.m4a"
        total_time = round(time.time() - start_time, 1)

        await message.reply_audio(
            audio=output_path,
            title=new_file_name,
            caption=(
                f"✅ **Converted Successfully!**\n\n"
                f"🎵 Format: M4A (AAC)\n"
                f"🎚 Bitrate: {settings['bitrate']}\n"
                f"🔊 Channels: Stereo\n"
                f"🎚 Sample Rate: {settings['ar']} Hz\n"
                f"📦 Size: {out_size} MB\n"
                f"⏱ Total time: {total_time}s"
            ),
            progress=progress,
            progress_args=(status_msg, "⬆️ **Uploading...**")
        )
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(
            f"❌ **Error:** {str(e)}\n"
            "Please try again."
        )

    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        last_update_time.pop(message.id, None)

# ==========================================
# BOT START
# ==========================================
if __name__ == '__main__':
    # Start Render health check server
    health_thread = threading.Thread(
        target=run_health_server, daemon=True)
    health_thread.start()

    print("🤖 Bot is starting...")
    app.run()
