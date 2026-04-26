"""
voice_handler.py - Voice Message Handling and Text Parsing (Pure Python - No API)
תפקיד: ניתוח מלאי בעברית ללא צורך בשרותים חיצוניים
"""

import re
from typing import Dict, Optional

# מיפוי קודים קצרים לשמות מוצרים מלאים
PRODUCT_SHORT_CODES = {
    "ר": "רוגלך שוקולד",
    "ג": "גביניות",
    "ח": "חלות מתוק",
    "פ": "פס שמרים קקאו שקית",
    "קר": "קראנץ' קקאו",
    "קו": "קוקוש קייק",
    "שג": "פס שמרים גבינה",
    "פי": "פס שוקולד פירורים",
    "ע": "רוגלך עלים קקאו",
}

# מיפוי מילים חלקיות לשמות מוצרים מלאים
PRODUCT_KEYWORDS = {
    "חלות": "חלות מתוק",
    "ח\"מ": "חלות מתוק",
    "רוגלך": "רוגלך שוקולד",
    "רוגלך שוקולד": "רוגלך שוקולד",
    "ר\"ש": "רוגלך שוקולד",
    "רוגלך עלים": "רוגלך עלים קקאו",
    "רוג עלים": "רוגלך עלים קקאו",
    "ר\"ע": "רוגלך עלים קקאו",
    "קוקוש": "קוקוש קייק",
    "קק": "קוקוש קייק",
    "קראנץ": "קראנץ' קקאו",
    "קר": "קראנץ' קקאו",
    "גביניות": "גביניות",
    "גבינ": "גביניות",
    "ג": "גביניות",
    "פס שמרים גבינה": "פס שמרים גבינה",
    "פ\"ג": "פס שמרים גבינה",
    "פס גבינה": "פס שמרים גבינה",
    "פס שמרים קקאו": "פס שמרים קקאו שקית",
    "פ\"ק": "פס שמרים קקאו שקית",
    "פס קקאו": "פס שמרים קקאו שקית",
    "פס שוקולד": "פס שוקולד פירורים",
    "פ\"ש": "פס שוקולד פירורים",
}


class HebrewInventoryParser:
    """ניתוח טקסט עברי ללא צורך בClaude API"""

    @staticmethod
    def parse_inventory_text(text: str) -> Dict[str, int]:
        """
        ניתוח טקסט עברי שמתאר מלאי

        תמיכה בפורמטים:
        - "נשאר 3 רוגלך, 2 גביניות, 4 חלות"
        - "ר3 ג2 ח4"
        - "רוגלך שוקולד 3 גביניות 2"
        - "3 רוגלך שוקולד"

        Args:
            text: הודעה בעברית המתארת מלאי

        Returns:
            dict: {product_name: quantity}
        """
        if not text or not isinstance(text, str):
            return {}

        # נקה את הטקסט
        text = text.strip()

        inventory = {}

        # נסיון 1: חיפוש של קוד קצר + מספר (ר3, ג2, וכו')
        # זה הפורמט המדויק ביותר
        short_code_matches = re.findall(r'([א-ת]+)\s*([0-9]+)', text)
        for code, qty in short_code_matches:
            product = HebrewInventoryParser._match_product(code)
            if product:
                inventory[product] = int(qty)

        # אם וצאנו קודים קצרים, חזור כבר
        if inventory:
            return inventory

        # נסיון 2: הסר מילים זרות וחפש בפורמט חופשי יותר
        clean_text = HebrewInventoryParser._clean_text(text)

        # חפש patterns כמו "product_name number" או "number product_name"
        # מחפשים שם כל מוצר בטקסט ויחד עם מספר
        all_products = list(set(PRODUCT_KEYWORDS.values()))

        for product_name in all_products:
            # חפש את שם המוצר בטקסט (בדיוק או חלקית)
            keywords_for_product = [k for k, v in PRODUCT_KEYWORDS.items() if v == product_name]

            for keyword in keywords_for_product:
                # חפש "keyword number" pattern
                pattern = re.escape(keyword) + r'\s*([0-9]+)'
                match = re.search(pattern, clean_text, re.IGNORECASE)
                if match:
                    qty = int(match.group(1))
                    if product_name not in inventory:
                        inventory[product_name] = qty
                    break

                # חפש "number keyword" pattern
                pattern = r'([0-9]+)\s+' + re.escape(keyword)
                match = re.search(pattern, clean_text, re.IGNORECASE)
                if match:
                    qty = int(match.group(1))
                    if product_name not in inventory:
                        inventory[product_name] = qty
                    break

        return inventory

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        ניקוי טקסט ממילים זרות וסימנים
        """
        # הסר מילים זרות נפוצות
        stop_words = [
            "נשאר", "יש", "בדיוק", "בערך", "סה״כ", "כל", "ו",
            "על", "המדף", "בחנות", "כרגע", "רק", "לעדכן"
        ]

        for word in stop_words:
            text = re.sub(r'\b' + word + r'\b', ' ', text)

        # הסר סימני פיסוק (פחות מילים שימושיות)
        text = re.sub(r'[,;:\(\)]', ' ', text)

        # הסר רווחים כפולים
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    @staticmethod
    def _match_product(product_text: str) -> Optional[str]:
        """
        ניסיון להתאים טקסט לשם מוצר קיים

        Args:
            product_text: טקסט אפשרי של מוצר

        Returns:
            str: שם מוצר מלא או None
        """
        if not product_text:
            return None

        product_text = product_text.strip()

        # בדוק תחילה קודים קצרים (בדיוש)
        if product_text in PRODUCT_SHORT_CODES:
            return PRODUCT_SHORT_CODES[product_text]

        # בדוק תחילה התאמות בעברית (כולל דיאקריטיקס)
        for keyword, product_name in PRODUCT_KEYWORDS.items():
            if keyword == product_text:
                return product_name

        # בדוק התאמה חלקית
        product_text_lower = product_text.lower()
        for keyword, product_name in PRODUCT_KEYWORDS.items():
            if keyword.lower() in product_text_lower:
                return product_name

        return None


# פונקציות תאימות לחיצוני
class VoiceTranscriber:
    """ממשק תאימות - קול אינו נתמך, השתמש בטקסט"""

    def __init__(self, api_key: Optional[str] = None):
        pass

    async def transcribe_and_parse(self, voice_file_path: str) -> Dict[str, int]:
        return {"error": "אנא שלח טקסט געם חיצוני"}


async def parse_inventory_text(text: str) -> Dict[str, int]:
    """פרסור משופר של טקסט מלאי — תומך בכל הפורמטים הנפוצים"""
    if not text or not isinstance(text, str):
        return {}

    # נרמול: החלף פסיקים ומפרידים ברווח
    normalized = re.sub(r'[,;/|\\]', ' ', text.strip())
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # פצל לטוקנים: מילים עבריות ומספרים
    tokens = re.findall(r'[\u05d0-\u05ea]+|[0-9]+', normalized)

    inventory = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.isdigit():
            # מספר ראשון: חפש מילים עבריות אחריו
            qty = int(token)
            j = i + 1
            words = []
            while j < len(tokens) and not tokens[j].isdigit():
                words.append(tokens[j])
                j += 1
            found = False
            for length in range(min(len(words), 3), 0, -1):
                phrase = ' '.join(words[:length])
                product = HebrewInventoryParser._match_product(phrase)
                if product:
                    inventory[product] = qty
                    i = i + 1 + length
                    found = True
                    break
            if not found:
                i += 1
        else:
            # מילה עברית ראשונה: אסוף מילים ואז מספר
            words = []
            j = i
            while j < len(tokens) and not tokens[j].isdigit():
                words.append(tokens[j])
                j += 1
            if j < len(tokens) and tokens[j].isdigit():
                qty = int(tokens[j])
                found = False
                for length in range(min(len(words), 3), 0, -1):
                    phrase = ' '.join(words[:length])
                    product = HebrewInventoryParser._match_product(phrase)
                    if product:
                        inventory[product] = qty
                        i = j + 1
                        found = True
                        break
                if not found:
                    i = j + 1
            else:
                i = j if j > i else i + 1

    return inventory


async def download_voice_file(file_path: str, bot_token: str, file_id: str) -> str:
    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        file = await bot.get_file(file_id)
        await file.download_to_drive(file_path)
        return file_path
    except Exception as e:
        print(f"Error downloading voice file: {e}")
        return None


async def transcribe_voice_with_api(voice_file_path: str, api_key: str) -> str:
    return None
