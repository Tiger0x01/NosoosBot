import asyncio
import os
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from cachetools import TTLCache
from aiohttp import web
from config import TELEGRAM_TOKEN, logger
from media_handler import fetch_video_data, get_transcript_text
from text_cleaner import clean_text
from doc_generator import generate_files, generate_summary_pdf
from ai_service import generate_summary, close_session

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# حماية الذاكرة والـ Rate Limit
user_video_data = TTLCache(maxsize=1000, ttl=900)
# Rate Limit: 5 طلبات كحد أقصى كل دقيقة للمستخدم
user_rate_limit = TTLCache(maxsize=1000, ttl=60)
# إحصائيات البوت
bot_stats = {"processed": 0, "errors": 0}

def generate_langs_keyboard(langs, page=0, page_size=30):
    start, end = page * page_size, page * page_size + page_size
    keyboard_buttons = []
    row = []
    for lang in langs[start:end]:
        row.append(InlineKeyboardButton(text=lang["name"], callback_data=f"lang_{lang['code']}"))
        if len(row) == 2:
            keyboard_buttons.append(row)
            row = []
    if row: keyboard_buttons.append(row)
    
    # زر البحث عن لغة
    keyboard_buttons.append([InlineKeyboardButton(text="🔍 بحث عن لغة (قريباً)", callback_data="search_lang")])
        
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️ السابق", callback_data=f"page_{page-1}"))
    if end < len(langs): nav_row.append(InlineKeyboardButton(text="التالي ➡️", callback_data=f"page_{page+1}"))
    if nav_row: keyboard_buttons.append(nav_row)
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def check_rate_limit(user_id):
    """التحقق من عدم تجاوز 5 طلبات في الدقيقة"""
    history = user_rate_limit.get(user_id, [])
    now = time.time()
    history = [t for t in history if now - t < 60]
    if len(history) >= 5: return False
    history.append(now)
    user_rate_limit[user_id] = history
    return True

@dp.message(Command("start", "help", "about", "stats"))
async def commands_handler(message: types.Message):
    cmd = message.text.split()[0].lower()

    if cmd == "/start":
        await message.answer(
            "👋 *مرحبًا بك في NosoosBot*\n\n"
            "🎥 أرسل رابط أي فيديو من YouTube وسأقوم بـ:\n\n"
            "• استخراج النص (Captions)\n"
            "• تحويله إلى ملفات TXT / PDF / DOCX\n"
            "• تلخيصه بالذكاء الاصطناعي\n\n"
            "ℹ️ لمعرفة طريقة الاستخدام أرسل /help",
            parse_mode="Markdown"
        )

    elif cmd == "/help":
        await message.answer(
            "📖 *طريقة الاستخدام*\n\n"
            "1️⃣ أرسل رابط فيديو YouTube.\n"
            "2️⃣ اختر لغة التفريغ.\n"
            "3️⃣ سيتم استخراج النص وإنشاء الملفات.\n"
            "4️⃣ يمكنك الحصول على ملخص بالذكاء الاصطناعي.\n\n"
            "ℹ️ لمعرفة المزيد عن البوت أرسل /about",
            parse_mode="Markdown"
        )

    elif cmd == "/about":
        await message.answer(
            "📄 *NosoosBot*\n\n"
            "بوت لاستخراج نصوص YouTube (Captions)، "
            "وتحويلها إلى ملفات احترافية، مع إمكانية تلخيص المحتوى بالذكاء الاصطناعي.\n\n"
            "👨‍💻 Developed by *Mohamed Elnemr*\n\n"
            "🔗 GitHub\n"
            "github.com/Tiger0x01\n\n"
            "🔗 LinkedIn\n"
            "linkedin.com/in/tiger0x01",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    elif cmd == "/stats":
        await message.answer(
            f"📊 *Bot Statistics*\n\n"
            f"✅ Processed Videos: {bot_stats['processed']}\n"
            f"❌ Errors: {bot_stats['errors']}",
            parse_mode="Markdown"
        )

@dp.message(F.text.regexp(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"))
async def handle_url(message: types.Message):
    user_id = message.from_user.id
    if not check_rate_limit(user_id):
        await message.reply("⏳ تجاوزت الحد المسموح! يرجى الانتظار لمدة دقيقة.")
        return

    msg = await message.reply("🔍 *جاري فحص الفيديو...*", parse_mode="Markdown")
    try:
        # استخدام Async Wrapper لمنع الـ Blocking
        loop = asyncio.get_event_loop()
        video_data = await loop.run_in_executor(None, fetch_video_data, message.text)
        user_video_data[user_id] = video_data
        
        # إرسال الصورة المصغرة (Thumbnail)
        if video_data['thumbnail']:
            await message.answer_photo(photo=video_data['thumbnail'], caption=f"🎬 *{video_data['title']}*", parse_mode="Markdown")
            await msg.delete() # حذف رسالة الفحص وترك الصورة
            msg = await message.answer("🌍 *اختر لغة التفريغ:*", reply_markup=generate_langs_keyboard(video_data['langs']), parse_mode="Markdown")
        else:
            await msg.edit_text(f"🎬 *{video_data['title']}*\n\n🌍 *اختر لغة التفريغ:*", reply_markup=generate_langs_keyboard(video_data['langs']), parse_mode="Markdown")

    except Exception as e:
        logger.exception("URL Checking Error")
        await msg.edit_text(f"❌ *{str(e)}*", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("page_"))
async def page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[1])
    user_data = user_video_data.get(callback.from_user.id)
    if user_data:
        await callback.message.edit_reply_markup(reply_markup=generate_langs_keyboard(user_data["langs"], page=page))

@dp.callback_query(F.data == "search_lang")
async def search_lang_callback(callback: types.CallbackQuery):
    await callback.answer("ميزة البحث ستتوفر قريباً! الرجاء استخدام الأزرار حالياً.", show_alert=True)

@dp.callback_query(F.data.startswith("lang_"))
async def process_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang_code = callback.data.split("_")[1]
    user_data = user_video_data.get(user_id)
    
    if not user_data:
        await callback.answer("⏳ انتهت الجلسة. أرسل الرابط مجدداً.", show_alert=True)
        return

    msg = await callback.message.edit_text("✅ *جاري قراءة الترجمة...*\n⏳ تنظيف النص\n⏳ إنشاء الملفات\n⏳ التلخيص الذكي", parse_mode="Markdown")
    files_to_delete = []

    try:
        loop = asyncio.get_event_loop()
        raw_text = await loop.run_in_executor(None, get_transcript_text, user_data["id"], lang_code)
        formatted_text = clean_text(raw_text)
        
        await msg.edit_text("✅ *تمت القراءة*\n✅ *تم التنظيف*\n⏳ إنشاء الملفات (TXT, PDF, DOCX)\n⏳ التلخيص الذكي", parse_mode="Markdown")

        txt, pdf, docx = await loop.run_in_executor(None, generate_files, formatted_text, f"{user_id}_{lang_code}", user_data["title"], user_data["url"], lang_code)
        files_to_delete.extend([txt, pdf, docx])
        
        await msg.edit_text("✅ *تمت القراءة*\n✅ *تم التنظيف*\n✅ *الملفات جاهزة (جاري الإرسال)*\n⏳ التلخيص الذكي يقرأ ويحلل الآن...", parse_mode="Markdown")
        
        summary_task = asyncio.create_task(generate_summary(formatted_text))
        
        await asyncio.gather(
            bot.send_document(callback.message.chat.id, FSInputFile(txt), caption="📄 النص (TXT)"),
            bot.send_document(callback.message.chat.id, FSInputFile(pdf), caption="📕 النص (PDF)"),
            bot.send_document(callback.message.chat.id, FSInputFile(docx), caption="📘 النص (DOCX)")
        )
        
        summary_result = await summary_task
        
        if summary_result.startswith("❌"):
            await msg.edit_text(summary_result)
        else:
            summary_pdf_path = await loop.run_in_executor(None, generate_summary_pdf, summary_result, user_data['title'], user_id)
            files_to_delete.append(summary_pdf_path)
            
            await msg.edit_text("✅ *اكتملت العملية بنجاح!*\nإليك ملخص الفيديو:", parse_mode="Markdown")
            await bot.send_document(callback.message.chat.id, FSInputFile(summary_pdf_path), caption="📝 ملخص الذكاء الاصطناعي (PDF)")

        bot_stats["processed"] += 1

    except Exception as e:
        bot_stats["errors"] += 1
        logger.exception("Processing Error")
        await msg.edit_text(f"❌ *حدث خطأ أثناء المعالجة: {str(e)}*", parse_mode="Markdown")
    finally:
        # ضمان إزالة الملفات دائماً (Try/Finally)
        for f in files_to_delete:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass

async def on_shutdown(dispatcher):
    logger.info("جاري إغلاق البوت وإغلاق الجلسات...")
    await close_session()

async def main():
    logger.info("البوت يعمل الآن")
    dp.shutdown.register(on_shutdown) # تسجيل عملية الإغلاق الآمن للـ Sessions
    await dp.start_polling(bot)



async def start_web_server():
    app = web.Application()
    app.router.add_get('/', lambda request: web.Response(text="NosoosBot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

if __name__ == "__main__":
    asyncio.run(main())