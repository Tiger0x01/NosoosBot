import json
import urllib.request
import pycountry
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import (
    YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
)
from cachetools import TTLCache

# كاش موحد لحفظ معلومات الفيديو واللغات لمدة ساعة (سعة 1000)
yt_cache = TTLCache(maxsize=1000, ttl=3600)

def format_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0: return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"
    return f"{int(minutes):02d}:{int(secs):02d}"

def extract_video_id(url):
    parsed = urlparse(url)
    if parsed.hostname == 'youtu.be': return parsed.path[1:]
    if parsed.hostname in ('www.youtube.com', 'youtube.com'):
        return parse_qs(parsed.query).get('v', [None])[0]
    return None

def get_language_flag(code):
    try:
        # محاولة جلب الدولة من كود اللغة للحصول على علم تقريبي
        lang = pycountry.languages.get(alpha_2=code[:2])
        if lang:
            # طريقة رياضية بسيطة لتحويل كود من حرفين لعلم (Regional Indicator)
            country_code = code[:2].upper()
            if country_code == 'EN': country_code = 'US'
            if country_code == 'AR': country_code = 'EG'
            return chr(ord(country_code[0]) + 127397) + chr(ord(country_code[1]) + 127397)
    except: pass
    return "🌍"

def beautify_language_name(code, name):
    clean_name = name.replace("(auto-generated)", "").replace("(Auto-generated)", "").strip()
    return f"{get_language_flag(code)} {clean_name}"

def fetch_video_data(url):
    """دالة واحدة تجلب العنوان، الصورة، واللغات معاً لتجنب التكرار"""
    video_id = extract_video_id(url)
    if not video_id: raise ValueError("رابط يوتيوب غير صحيح.")
    if video_id in yt_cache: return yt_cache[video_id]

    try:
        # 1. جلب المعلومات الأساسية من OEmbed
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        with urllib.request.urlopen(oembed_url) as resp:
            data = json.loads(resp.read().decode())
            title = data.get("title", "YouTube Video")
            thumbnail = data.get("thumbnail_url", "")
    except Exception:
        title, thumbnail = "YouTube Video", ""

    # 2. جلب اللغات
    try:
        api = YouTubeTranscriptApi()
        # ✅ التعديل الأول: استخدام .list بدلاً من .list_transcripts
        transcript_list = api.list(video_id)

        languages = {}
        for t in transcript_list:
            languages[t.language_code] = {"code": t.language_code, "name": beautify_language_name(t.language_code, t.language)}
            if t.is_translatable:
                for lang in t.translation_languages:
                    # ✅ التعديل الثاني: التعامل معها كـ Objects وليس Dictionaries
                    code = lang.language_code
                    name = lang.language

                    languages.setdefault(
                        code,
                        {
                            "code": code,
                            "name": beautify_language_name(code, name)
                        }
                    )
        
        result = {"id": video_id, "title": title, "thumbnail": thumbnail, "url": url, "langs": list(languages.values()), "transcript_obj": transcript_list}
        yt_cache[video_id] = result
        return result

    except TranscriptsDisabled: raise Exception("الترجمة مغلقة في هذا الفيديو (TranscriptsDisabled).")
    except NoTranscriptFound: raise Exception("لا يوجد ترجمة لهذا الفيديو (NoTranscriptFound).")
    except VideoUnavailable: raise Exception("الفيديو غير متاح أو محذوف.")
    except Exception as e: raise Exception(f"خطأ من يوتيوب: {e}")

def get_transcript_text(video_id, lang_code):
    try:
        cached_data = yt_cache.get(video_id)
        if cached_data:
            transcript_list = cached_data["transcript_obj"]
        else:
            # ✅ التعديل الثالث: استخدام .list هنا أيضاً
            transcript_list = YouTubeTranscriptApi().list(video_id)
        
        try: transcript = transcript_list.find_transcript([lang_code])
        except: transcript = next((t.translate(lang_code) for t in transcript_list if t.is_translatable), None)
        if not transcript: raise Exception("اللغة غير متاحة.")

        transcript_data = transcript.fetch(preserve_formatting=True)
        grouped_lines, current_minute, current_text = [], -1, []
        
        for item in transcript_data:
            # ✅ التعديل الرابع: الوصول للبيانات عن طريق Object Attributes
            text = item.text.strip()
            if not text: continue
            
            minute = int(item.start // 60)
            
            if minute != current_minute:
                if current_text: grouped_lines.append(f"[{format_time(current_minute * 60)}] {' '.join(current_text)}")
                current_minute, current_text = minute, [text]
            else: current_text.append(text)

        if current_text: grouped_lines.append(f"[{format_time(current_minute * 60)}] {' '.join(current_text)}")
        return "\n\n".join(grouped_lines)
        
    except Exception as e: raise Exception(f"فشل جلب النص: {str(e)}")