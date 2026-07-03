import asyncio
import aiohttp
import textwrap
from config import GROQ_API_KEY, logger

_session = None
# Semaphore يحد من الطلبات المتزامنة (5 كحد أقصى) لتجنب 429 Too Many Requests
_semaphore = asyncio.Semaphore(5)

def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()

async def fetch_summary_from_api(text_chunk: str, system_prompt: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text_chunk}
        ],
        "stream": False
    }

    session = get_session()
    for attempt in range(3):
        try:
            async with _semaphore:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status in [429, 500, 503]:
                        await asyncio.sleep(2 ** attempt)  # Exponential Backoff
                        continue
                    data = await response.json()
                    if response.status != 200:
                        logger.error(f"Groq API Error: {data}")
                        return "❌ خطأ في الخادم."
                    return data["choices"][0]["message"]["content"]
        except asyncio.TimeoutError:
            if attempt == 2: return "❌ انتهت مهلة الاتصال."
        except Exception as e:
            logger.exception("AI Service Exception")
            return "❌ خطأ غير متوقع."
    return "❌ فشل التلخيص بعد 3 محاولات."

async def generate_summary(text: str) -> str:
    # Chunking الحقيقي: تقسيم النص إلى أجزاء (مثلاً 6000 حرف للجزء)
    chunk_size = 6000
    chunks = textwrap.wrap(text, chunk_size, replace_whitespace=False, break_long_words=False)
    
    if len(chunks) == 1:
        # فيديو قصير: تلخيص مباشر
        return await fetch_summary_from_api(
            chunks[0], 
            "قم بتلخيص النص التالي باللغة العربية بشكل احترافي ومنظم باستخدام نقاط (Summary, Main Idea, Important Points, Final Notes)."
        )
    
    # فيديو طويل: تلخيص كل جزء بالتوازي
    tasks = [fetch_summary_from_api(c, "لخص أهم النقاط في هذا الجزء من الفيديو باللغة العربية.") for c in chunks[:5]] # حد أقصى 5 أجزاء تجنباً للحدود
    chunk_summaries = await asyncio.gather(*tasks)
    
    combined_summaries = "\n\n".join([s for s in chunk_summaries if not s.startswith("❌")])
    if not combined_summaries.strip(): return "❌ فشل التلخيص الكلي."

    # تلخيص الملخصات (Map-Reduce)
    final_prompt = f"هذه ملخصات لأجزاء من فيديو واحد. ادمجهم في ملخص نهائي متماسك واحترافي مقسم لعناصر:\n\n{combined_summaries}"
    return await fetch_summary_from_api(final_prompt, "أنت مساعد ذكي تدمج وتلخص النصوص باحترافية.")