import os
import re
import logging
import threading
import instaloader
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

L = instaloader.Instaloader(
    dirname_pattern="downloads/{target}",
    save_metadata=False,
    download_comments=False,
    download_video_thumbnails=False,
    post_metadata_txt_pattern="",
)


# ---- Dummy HTTP server (Render Web Service ke liye port bind karna zaroori hai) ----
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return  # silent


def run_web():
    server = HTTPServer(("0.0.0.0", PORT), PingHandler)
    logger.info(f"HTTP server on port {PORT}")
    server.serve_forever()


# ---- Telegram handlers ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Namaste!\n\n"
        "Mujhe koi bhi Instagram *username* bhejo (bina @ ke),\n"
        "main uske latest Reels & Posts download karke bhej dunga.\n\n"
        "Example: `natgeo`",
        parse_mode="Markdown",
    )


async def handle_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lstrip("@")
    username = re.sub(r"[^A-Za-z0-9_.]", "", text)

    if not username:
        await update.message.reply_text("❌ Sahi username bhejo.")
        return

    msg = await update.message.reply_text(
        f"⏳ `{username}` ke posts fetch ho rahe hain...", parse_mode="Markdown"
    )

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        await msg.edit_text(f"❌ Profile nahi mila: {e}")
        return

    count = 0
    max_posts = 5

    try:
        for post in profile.get_posts():
            if count >= max_posts:
                break

            target_dir = f"downloads/{username}"
            os.makedirs(target_dir, exist_ok=True)

            try:
                L.download_post(post, target=username)
            except Exception as e:
                logger.warning(f"Download fail: {e}")
                continue

            caption = (post.caption or "")[:900]
            caption = f"📸 @{username}\n\n{caption}"

            for fname in sorted(os.listdir(target_dir)):
                fpath = os.path.join(target_dir, fname)
                try:
                    if fname.endswith(".mp4"):
                        with open(fpath, "rb") as f:
                            await update.message.reply_video(f, caption=caption)
                        count += 1
                        os.remove(fpath)
                        break
                    elif fname.endswith((".jpg", ".jpeg", ".png")):
                        with open(fpath, "rb") as f:
                            await update.message.reply_photo(f, caption=caption)
                        count += 1
                        os.remove(fpath)
                        break
                except Exception as e:
                    logger.warning(f"Send fail: {e}")
                finally:
                    if os.path.exists(fpath):
                        os.remove(fpath)

        if count == 0:
            await msg.edit_text("⚠️ Koi post download nahi ho payi (private/rate-limit ho sakta hai).")
        else:
            await msg.edit_text(f"✅ {count} posts bhej diye!")

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env var set karo.")

    # HTTP server background thread me start karo (Render web service ke liye)
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username))

    logger.info("Bot chal raha hai...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
