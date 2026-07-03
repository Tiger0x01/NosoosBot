import re

def remove_noise(text):
    # نستخدم Negative Lookahead عشان نتجاهل الأقواس اللي جواها أرقام (الوقت)
    # وبكدا هيمسح [Music] بس هيسيب [00:15]
    text = re.sub(r"\[(?!\d{2}:\d{2}).*?\]", "", text)
    return text

def remove_symbols(text):
    text = text.replace(">>", "")
    text = text.replace(">", "")
    text = text.replace("♪", "")
    text = text.replace("♫", "")
    
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    
    return text
def remove_duplicate_words(text):
    text = re.sub(
        r"\b(\w+)( \1){2,}",
        r"\1",
        text,
        flags=re.IGNORECASE
    )
    return text

def normalize_spaces(text):
    text = re.sub(r"[ \t]+", " ", text)
    # تقليل المسافات الفارغة المبالغ فيها
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def restore_paragraphs(text):
    return text

def final_cleanup(text):
    return text.strip()

def clean_text(text):
    text = remove_noise(text)
    text = remove_symbols(text)
    text = remove_duplicate_words(text)
    text = normalize_spaces(text)
    text = restore_paragraphs(text)
    text = final_cleanup(text)
    return text