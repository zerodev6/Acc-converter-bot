import os
import asyncio
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
last_update_time = {}

# ==========================================
# HEALTH SERVER
# ==========================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ==========================================
# PROGRESS BAR
# ==========================================
def make_bar(percent):
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)

async def progress(current, total, status_msg, action):
    now = time.time()
    uid = status_msg.id
    if now - last_update_time.get(uid, 0) < 2:
        return
    last_update_time[uid] = now
    pct = int((current / total) * 100) if total else 0
    done = round(current / 1024 / 1024, 1)
    total_mb = round(total / 1024 / 1024, 1)
    try:
        await status_msg.edit_text(
            f"{action}\n"
            f"[{make_bar(pct)}] {pct}%\n"
            f"📦 {done} MB / {total_mb} MB"
        )
    except:
        pass

# ==========================================
# SETTINGS
# ==========================================
def get_settings(user_id):
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = {
            'bitrate': '320k',
            'ar': '48000',
            'ac': '2'
        }
    return USER_SETTINGS[user_id]

def make_markup(s):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🎵 Bitrate: {s['bitrate']}",
            callback_data="toggle_bitrate")],
        [InlineKeyboardButton(
            f"🎚 Sample Rate: {s['ar']} Hz",
            callback_data="toggle_ar")],
        [InlineKeyboardButton(
            f"🔊 Channels: {'Stereo' if s['ac']=='2' else 'Mono'}",
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
        "📊 Progress bar included\n"
        "📤 Get M4A back instantly\n\n"
        "📌 /help — How to use\n"
        "⚙️ /settings — Change quality"
    )

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "🛠 **How to use:**\n\n"
        "1️⃣ Send or forward any audio/video\n"
        f"2️⃣ Supported: {', '.join(SUPPORTED_FORMATS).upper()}\n"
        "3️⃣ Watch the progress bar\n"
        "4️⃣ Get your M4A file!\n\n"
        "📦 Max: **2GB**\n"
        "✅ 5.1 Surround → Clear Stereo\n"
        "⚙️ /settings to adjust quality"
    )

@app.on_message(filters.command("settings"))
async def settings_cmd(client, message):
    await message.reply_text(
        "⚙️ **Settings** — Tap to change:",
        reply_markup=make_markup(get_settings(message.from_user.id))
    )

@app.on_callback_query(filters.regex("^toggle_"))
async def toggle(client, cq):
    s = get_settings(cq.from_user.id)
    if cq.data == "toggle_bitrate":
        opts = ['128k', '192k', '320k']
        s['bitrate'] = opts[(opts.index(s['bitrate']) + 1) % 3]
    elif cq.data == "toggle_ar":
        opts = ['44100', '48000']
        s['ar'] = opts[(opts.index(s['ar']) + 1) % 2]
    elif cq.data == "toggle_ac":
        s['ac'] = '1' if s['ac'] == '2' else '2'
    USER_SETTINGS[cq.from_user.id] = s
    await cq.message.edit_reply_markup(make_markup(s))
    await cq.answer("✅ Updated!")

# ==========================================
# CONVERSION PROGRESS READER
# ==========================================
async def run_ffmpeg_with_progress(cmd, duration, status_msg):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE
    )

    last_update = 0
    error_lines = []

    while True:
        line = await process.stderr.readline()
        if not line:
            break
        line = line.decode('utf-8', errors='ignore').strip()
        error_lines.append(line)

        # Parse FFmpeg time= from stderr
        if 'time=' in line and duration > 0:
            try:
                t = line.split('time=')[1].split(' ')[0]
                h, m, s = t.split(':')
                current = float(h)*3600 + float(m)*60 + float(s)
                pct = min(int((current / duration) * 100), 99)
                now = time.time()
                if now - last_update >= 3:
                    last_update = now
                    elapsed = round(now - last_update, 1)
                    cur_str = f"{int(float(h)):02}:{int(float(m)):02}:{int(float(s)):02}"
                    dur_str = f"{int(duration//3600):02}:{int((duration%3600)//60):02}:{int(duration%60):02}"
                    try:
                        await status_msg.edit_text(
                            f"🔄 **Converting to AAC M4A...**\n"
                            f"[{make_bar(pct)}] {pct}%\n"
                            f"⏱ {cur_str} / {dur_str}"
                        )
                    except:
                        pass
            except:
                pass

    await process.wait()
    return process.returncode, '\n'.join(error_lines[-20:])

# ==========================================
# GET DURATION
# ==========================================
async def get_duration(path):
    try:
        p = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await p.communicate()
        return float(out.decode().strip())
    except:
        return 0

# ==========================================
# MAIN FILE HANDLER
# ==========================================
@app.on_message(filters.audio | filters.video | filters.document)
async def handle_file(client, message):
    file_obj = message.audio or message.video or message.document
    file_name = getattr(file_obj, "file_name", "file")
    file_size = getattr(file_obj, "file_size", 0)
    ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''

    if ext not in SUPPORTED_FORMATS:
        await message.reply_text(
            "❌ **Unsupported format!**\n"
            f"✅ Supported: {', '.join(SUPPORTED_FORMATS).upper()}")
        return

    if file_size > MAX_FILE_SIZE:
        await message.reply_text("❌ Too large! Max **2GB**.")
        return

    size_mb = round(file_size / 1024 / 1024, 1)
    status = await message.reply_text(
        f"📥 **Downloading...**\n"
        f"[░░░░░░░░░░] 0%\n"
        f"📦 {size_mb} MB"
    )

    safe_id = str(message.id)
    inp = f"/tmp/input_{safe_id}.{ext}"
    out = f"/tmp/output_{safe_id}.m4a"
    t0 = time.time()

    try:
        # 1. DOWNLOAD
        await message.download(
            file_name=inp,
            progress=progress,
            progress_args=(status, "📥 **Downloading...**")
        )
        dl_time = round(time.time() - t0, 1)

        # 2. GET DURATION
        duration = await get_duration(inp)

        await status.edit_text(
            f"✅ Downloaded in {dl_time}s\n"
            f"🔄 **Converting...**\n"
            f"[░░░░░░░░░░] 0%\n"
            f"⏱ Starting..."
        )

        # 3. CONVERT - NO -progress flag, reads stderr
        s = get_settings(message.from_user.id)
        cmd = [
            'ffmpeg', '-y',
            '-i', inp,
            '-threads', '4',
            '-c:a', 'aac',
            '-b:a', s['bitrate'],
            '-ac', '2',
            '-af', 'pan=stereo|FL=FC+0.707*FL+0.707*BL|FR=FC+0.707*FR+0.707*BR',
            '-ar', s['ar'],
            '-vn',
            '-movflags', '+faststart',
            out
        ]

        ct0 = time.time()
        rc, err = await run_ffmpeg_with_progress(cmd, duration, status)

        if rc != 0:
            await status.edit_text(
                f"❌ **FFmpeg Error:**\n`{err[-300:]}`")
            return

        conv_time = round(time.time() - ct0, 1)
        out_mb = round(os.path.getsize(out) / 1024 / 1024, 1)
        total_time = round(time.time() - t0, 1)

        await status.edit_text(
            f"✅ Converted in {conv_time}s\n"
            f"⬆️ **Uploading...**\n"
            f"[░░░░░░░░░░] 0%\n"
            f"📦 {out_mb} MB"
        )

        # 4. UPLOAD
        await message.reply_audio(
            audio=out,
            title=file_name.rsplit('.', 1)[0] + '.m4a',
            caption=(
                f"✅ **Done!**\n\n"
                f"🎵 AAC M4A\n"
                f"🎚 {s['bitrate']} | {s['ar']} Hz | Stereo\n"
                f"📦 {out_mb} MB\n"
                f"⏱ {total_time}s total"
            ),
            progress=progress,
            progress_args=(status, "⬆️ **Uploading...**")
        )
        await status.delete()

    except Exception as e:
        await status.edit_text(f"❌ **Error:** {str(e)}")

    finally:
        for f in [inp, out]:
            if os.path.exists(f):
                os.remove(f)
        last_update_time.pop(status.id, None)

# ==========================================
# START
# ==========================================
if __name__ == '__main__':
    threading.Thread(
        target=run_health_server, daemon=True).start()
    print("🤖 Starting bot...")
    app.run()
