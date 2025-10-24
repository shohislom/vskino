# bot_video_by_code.py
import logging
import sqlite3
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ========== SOZLAMALAR ==========
BOT_TOKEN = "8021664103:AAE8CJraPA-77JN09Qgmz1-gN7YjwvhQ16I"
CHANNELS = ["@vodiy_smartfon", "@andijonim_elonlar"]
ADMINS = {1054249508}
DB_PATH = "videos.db"
# ================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ========== DB FUNKSIYALAR ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            code TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_video(code: str, file_id: str, caption: Optional[str] = None) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR REPLACE INTO videos (code, file_id, caption) VALUES (?, ?, ?)",
            (code, file_id, caption),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.exception("DB save error: %s", e)
        return False
    finally:
        conn.close()


def get_video_by_code(code: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_id, caption FROM videos WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"file_id": row[0], "caption": row[1]}


# ========== OBUNA TEKSHIRUV ==========
async def check_subscription(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    results = {}
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            results[channel] = member.status in ("member", "creator", "administrator")
        except Exception as e:
            logger.error(f"{channel} tekshiruvda xato: {e}")
            results[channel] = False
    return results


# ========== KANAL HAVOLALARI ==========
async def send_channel_links_to_chat(chat_id: int, context: ContextTypes.DEFAULT_TYPE, not_joined=None):
    keyboard = []
    channels_to_show = not_joined or CHANNELS
    for ch in channels_to_show:
        name = ch.replace("@", "")
        keyboard.append([InlineKeyboardButton(f"📢 {name}", url=f"https://t.me/{name}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    channels_text = "\n".join([f"👉 {c}" for c in channels_to_show])
    text = (
        "⚠️ Videoni olish uchun quyidagi kanallarga obuna bo‘ling:\n\n"
        + channels_text
        + "\n\nObuna bo‘lgach, yana kodni yuboring."
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# ========== ADMIN TEKSHIRISH ==========
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# ========== HANDLERS ==========
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    subs = await check_subscription(context, user.id)
    not_joined = [ch for ch, joined in subs.items() if not joined]

    if not not_joined:
        await update.message.reply_text("🎬 Salom! Siz barcha kanallarga obunasiz. Endi video kodini yuboring.")
    else:
        await send_channel_links_to_chat(update.message.chat_id, context, not_joined)


async def add_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    msg = update.message
    video = msg.video or msg.document
    if not video:
        await msg.reply_text("Iltimos, videoni yuboring va captionga unga beriladigan kodni yozing (masalan: 123).")
        return

    caption = (msg.caption or "").strip()
    if not caption:
        await msg.reply_text("Video uchun caption (kod) kerak. Masalan: captionga `123` yozing.")
        return

    file_id = msg.video.file_id if msg.video else msg.document.file_id
    saved = save_video(code=caption, file_id=file_id, caption=caption)

    if saved:
        await msg.reply_text(f"✅ Video saqlandi. Kod: `{caption}`", parse_mode="Markdown")
    else:
        await msg.reply_text("❌ Xatolik yuz berdi — video saqlanmadi.")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    text = (msg.text or "").strip()

    if not text:
        return

    video = get_video_by_code(text)
    if not video:
        await msg.reply_text("❌ Bunday kod topilmadi. Iltimos, boshqa kod yuboring.")
        return

    subs = await check_subscription(context, user.id)
    not_joined = [ch for ch, joined in subs.items() if not joined]

    if not_joined:
        await send_channel_links_to_chat(msg.chat_id, context, not_joined)
        return

    try:
        await context.bot.send_video(chat_id=msg.chat_id, video=video["file_id"], caption=video.get("caption"))
    except Exception as e:
        logger.exception("Error sending video: %s", e)
        await msg.reply_text("❌ Video yuborishda xatolik yuz berdi.")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Botni ishga tushurish\n"
        "Admin: videoni botga yuboring va captionga kod yozing (masalan: 123)\n"
        "Foydalanuvchi: kod yuboradi, agar kanallarga obuna bo‘lsa — video yuboriladi."
    )


# ========== MAIN ==========
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.MimeType("video/mp4") | filters.Document.MimeType("video/"),
            add_video_handler,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    logger.info("✅ Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
