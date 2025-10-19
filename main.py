# -*- coding: utf-8 -*-
"""
World Savings Day Contest Bot (UZ/RU; file-based registry + video saving)

Features:
• Language choice (UZ/RU)
• Registration flow: greeting → university → study year → full name → phone → video
• File-based registry (JSON)
• Video downloading (saved under /videos)
• Admin DM notifications
• Admin commands: /whoami, /registered_count, /broadcast
"""

from __future__ import annotations
import os, json, asyncio, logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any

from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

# ---------- Config ----------
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN")

LOCAL_TZ = os.getenv("LOCAL_TZ", "Asia/Tashkent")
TZ = ZoneInfo(LOCAL_TZ)

REG_DB_PATH = Path(os.getenv("REG_DB_PATH", "data/contest.json"))
REG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

VIDEOS_DIR = Path("/tmp/videos")
VIDEOS_DIR.mkdir(exist_ok=True)


def parse_admins(raw: str | None) -> List[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

ORGANIZER_IDS = parse_admins(os.getenv("ORGANIZER_IDS", ""))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("world-savings-bot")

# ---------- Texts ----------
def t(lang: str, key: str) -> str:
    texts = {
        "start": {
            "uz": "👋 Salom! Bu bot orqali World Savings Day tanlovida ishtirok etish uchun videomavzuni yuborishingiz mumkin. Iltimos, quyidagi bosqichlarni ketma-ket bajaring.\n\n👉 Tilni tanlang:",
            "ru": "👋 Здравствуйте! С помощью этого бота вы можете отправить видеоролик для участия в конкурсе World Savings Day. Пожалуйста, выполните следующие шаги.\n\n👉 Выберите язык:",
        },
        "university": {
            "uz": "🎓 Universitetni tanlang:",
            "ru": "🎓 Выберите университет:",
        },
        "year": {
            "uz": "📚 Qaysi bosqichda o'qiysiz?",
            "ru": "📚 На каком курсе вы учитесь?",
        },
        "fullname": {
            "uz": "👤 To'liq ism-sharifingizni yozing (pasportdagidek):",
            "ru": "👤 Напишите полное имя и фамилию (как в паспорте):",
        },
        "phone": {
            "uz": "📞 Telefon raqamingizni yozing:",
            "ru": "📞 Напишите свой номер телефона:",
        },
        "video": {
            "uz": "🎥 Endi tanlov uchun videoni yuboring (MP4 formatda, sifatli bo‘lsin):",
            "ru": "🎥 Теперь отправьте видео для конкурса (в формате MP4, хорошего качества):",
        },
        "done": {
            "uz": "🎉 Barcha ma'lumotlaringiz va videongiz qabul qilindi. Rahmat!",
            "ru": "🎉 Вся информация и ваше видео получены. Спасибо!",
        },
        "invalid_video": {
            "uz": "❗ Iltimos, MP4 formatdagi video yuboring (fayl sifatida ham bo‘lishi mumkin).",
            "ru": "❗ Пожалуйста, отправьте видео в формате MP4 (можно как файл).",
        },
        "too_large": {
            "uz": "❗ Fayl hajmi juda katta. Iltimos, 200 MB dan kichik video yuboring.",
            "ru": "❗ Файл слишком большой. Отправьте видео размером до 200 МБ.",
        },
        "downloading": {
            "uz": "📥 Videongiz yuklanmoqda, biroz kuting...",
            "ru": "📥 Ваше видео загружается, пожалуйста, подождите...",
        },
        "download_error": {
            "uz": "⚠️ Videoni yuklab bo‘lmadi. Iltimos, keyinroq urinib ko‘ring.",
            "ru": "⚠️ Не удалось загрузить видео. Попробуйте позже.",
        },
    }
    return texts[key][lang if lang in ("uz", "ru") else "uz"]

# ---------- Registry ----------
def _load_registry() -> List[Dict[str, Any]]:
    if not REG_DB_PATH.exists():
        return []
    try:
        return json.loads(REG_DB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_registry(data: List[Dict[str, Any]]) -> None:
    REG_DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def add_record(rec: Dict[str, Any]):
    data = _load_registry()
    data.append(rec)
    _save_registry(data)

# ---------- States ----------
(LANG, UNI, YEAR, FULLNAME, PHONE, VIDEO) = range(6)

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="lang:uz"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru")]
    ])
    await update.message.reply_text(
        f"{t('uz', 'start')}\n\n{t('ru', 'start')}", reply_markup=kb
    )
    return LANG

async def on_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data.split(":")[1]
    context.user_data["lang"] = lang

    if lang == "uz":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Toshkent davlat iqtisodiyot universiteti", callback_data="uni:TDIU")],
            [InlineKeyboardButton("Qarshi davlat universiteti", callback_data="uni:QDU")],
            [InlineKeyboardButton("Qoraqalpoq davlat universiteti", callback_data="uni:KDU")],
            [InlineKeyboardButton("Farg‘ona davlat universiteti", callback_data="uni:FDU")],
        ])
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Ташкентский государственный экономический университет", callback_data="uni:TDIU")],
            [InlineKeyboardButton("Каршинский государственный университет", callback_data="uni:QDU")],
            [InlineKeyboardButton("Каракалпакский государственный университет", callback_data="uni:KDU")],
            [InlineKeyboardButton("Ферганский государственный университет", callback_data="uni:FDU")],
        ])

    await q.message.reply_text(t(lang, "university"), reply_markup=kb)
    return UNI

async def on_uni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["university"] = q.data.split(":")[1]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1-bosqich / 1 курс", callback_data="year:1")],
        [InlineKeyboardButton("2-bosqich / 2 курс", callback_data="year:2")],
        [InlineKeyboardButton("3-bosqich / 3 курс", callback_data="year:3")],
        [InlineKeyboardButton("4-bosqich / 4 курс", callback_data="year:4")],
    ])
    await q.message.reply_text(t(context.user_data["lang"], "year"), reply_markup=kb)
    return YEAR

async def on_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["year"] = q.data.split(":")[1]
    await q.message.reply_text(t(context.user_data["lang"], "fullname"))
    return FULLNAME

async def on_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fullname"] = update.message.text.strip()
    await update.message.reply_text(t(context.user_data["lang"], "phone"))
    return PHONE

async def on_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text(t(context.user_data["lang"], "video"))
    return VIDEO

# ---------- Video ----------
async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz")

    # Accept both Telegram video messages and attached files
    video_obj = update.message.video or (
        update.message.document if update.message.document and update.message.document.mime_type.startswith("video/") else None
    )

    if not video_obj:
        return await update.message.reply_text(t(lang, "invalid_video"))

    if video_obj.file_size and video_obj.file_size > 200 * 1024 * 1024:
        return await update.message.reply_text(t(lang, "too_large"))

    user = update.effective_user
    msg = await update.message.reply_text(t(lang, "downloading"))

    safe_name = (
        context.user_data.get("fullname", "unknown")
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )
    filename = f"{safe_name}_{user.id}_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
    filepath = VIDEOS_DIR / filename

    # --- Download with retry mechanism ---
    success = False
    last_error = None
    for attempt in range(3):
        try:
            file = await context.bot.get_file(video_obj.file_id)
            await file.download_to_drive(filepath)
            success = True
            break
        except Exception as e:
            last_error = e
            log.warning(f"Download attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(3)  # wait 3 seconds before next attempt

    if not success:
        log.error(f"Download failed after 3 attempts: {last_error}")
        return await msg.edit_text(
            "⚠️ "
            + ("Videoni yuklab bo‘lmadi. Iltimos, keyinroq urinib ko‘ring." if lang == "uz"
               else "⚠️ Не удалось загрузить видео даже после нескольких попыток. Попробуйте позже.")
        )

    # --- Save record in registry ---
    rec = {
        "id": user.id,
        "ts": datetime.now(TZ).isoformat(),
        "lang": lang,
        "university": context.user_data.get("university"),
        "year": context.user_data.get("year"),
        "fullname": context.user_data.get("fullname"),
        "phone": context.user_data.get("phone"),
        "video_file_id": video_obj.file_id,
        "video_path": str(filepath),
    }
    add_record(rec)

    await msg.edit_text(t(lang, "done"), reply_markup=ReplyKeyboardRemove())

    # --- Notify admins ---
    summary = (
        f"🆕 {'Yangi ishtirokchi' if lang == 'uz' else 'Новый участник'}:\n"
        f"🎓 {rec['university']}\n"
        f"📚 {rec['year']}-bosqich / курс\n"
        f"👤 {rec['fullname']}\n"
        f"📞 {rec['phone']}\n"
        f"🆔 {rec['id']}\n"
        f"🎥 Fayl / Файл: {filename}"
    )

    for aid in ORGANIZER_IDS:
        try:
            await context.bot.send_message(chat_id=aid, text=summary)
            await context.bot.forward_message(
                chat_id=aid,
                from_chat_id=update.message.chat.id,
                message_id=update.message.message_id,
            )
        except Exception as e:
            log.warning(f"Admin DM failed: {e}")

    return ConversationHandler.END


# ---------- Admin ----------
def _is_admin(uid: int) -> bool:
    return uid in ORGANIZER_IDS

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Sizning / Ваш user ID: {update.effective_user.id}")

async def registered_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await update.message.reply_text("Adminlar uchun / Только для админов.")
    data = _load_registry()
    await update.message.reply_text(f"Jami / Всего ishtirokchilar: {len(data)}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await update.message.reply_text("Adminlar uchun / Только для админов.")
    msg = update.message.text.partition(" ")[2].strip()
    if not msg:
        return await update.message.reply_text("Foydalanish: /broadcast <matn>\nИспользование: /broadcast <текст>")
    data = _load_registry()
    ok = fail = 0
    for r in data:
        try:
            await context.bot.send_message(chat_id=r["id"], text=msg)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await update.message.reply_text(f"Yuborildi / Отправлено: {ok}, Xato / Ошибка: {fail}")

# ---------- App ----------
def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(on_lang)],
            UNI: [CallbackQueryHandler(on_uni)],
            YEAR: [CallbackQueryHandler(on_year)],
            FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_fullname)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_phone)],
            VIDEO: [
                MessageHandler(filters.VIDEO, on_video),
                MessageHandler(filters.Document.VIDEO, on_video),
            ],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("registered_count", registered_count))
    app.add_handler(CommandHandler("broadcast", broadcast))
    return app

def main():
    log.info("World Savings Bot starting… Admins: %s", ORGANIZER_IDS)
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
