import re

# Comprehensive VTuber Proper Noun & Auto-Caption Typo Dictionary
# Maps common phonetic misspellings from YouTube auto-captions to correct VTuber names.
VTUBER_NAME_REPLACEMENTS = {
    r"\b[Cc]rony\b": "Kronii",
    r"\b[Cc]ronie\b": "Kronii",
    r"\b[Cc]allie\b": "Calliope",
    r"\b[Cc]allo\b": "Calliope",
    r"\b[Ff]awa\b": "Fuwawa",
    r"\b[Mm]oco\b": "Mococo",
    r"\b[Ff]uwamoko\b": "FUWAMOCO",
    r"\b[Bb]ay\b": "Bae",
    r"\b[Bb]ae\b": "Baelz",
    r"\b[Mm]umey\b": "Mumei",
    r"\b[Gg]oorah\b": "Gura",
    r"\b[Gg]ooru\b": "Gura",
    r"\b[Nn]erisa\b": "Nerissa",
    r"\b[Ss]hiori\b": "Shiori",
    r"\b[Zz]etta\b": "Zeta",
    r"\b[Kk]oboh\b": "Kobo",
    r"\b[Pp]ecora\b": "Pekora",
    r"\b[Mm]arin\b": "Marine",
    r"\b[Hh]olo\b": "Hololive",
}

VTUBER_GLOSSARY_PROMPT = """
VTUBER NAME & TERMINOLOGY DICTIONARY (CRITICAL CORRECTION GUIDE):
- "Kronii" / "Ouro Kronii" (NOT "Crony" or "Cronie")
- "FUWAMOCO" / "Fuwawa" / "Mococo" (NOT "Fuwamoko")
- "Gawr Gura" / "Gura" (NOT "Goorah")
- "Amelia Watson" / "Ame"
- "Ninomae Ina'nis" / "Ina"
- "Mori Calliope" / "Calli" / "Calliope"
- "Takanashi Kiara" / "Kiara"
- "IRyS"
- "Hakos Baelz" / "Bae"
- "Ceres Fauna" / "Fauna"
- "Ouro Kronii" / "Kronii"
- "Nanashi Mumei" / "Mumei"
- "Shiori Novella" / "Shiori"
- "Nerissa Ravencroft" / "Nerissa"
- "Koseki Bijou" / "Bijou" / "Biboo"
- "FUWAMOCO" (Fuwawa Abyssgard & Mococo Abyssgard)
- "Elizabeth Rose Bloodflame" / "Gigi Murin" / "Cecilia Immergreen" / "Raora Panthera"
- "Kobo Kanaeru" / "Kobo"
- "Vestia Zeta" / "Zeta"
- "Kaela Kovalskia" / "Kaela"
- "Ironmouse" / "Mousey"
- "Usada Pekora" / "Pekora"
- "Houshou Marine" / "Marine"
"""

def normalize_vtuber_transcript_text(text: str) -> str:
    """Pre-processes transcript text to replace common auto-caption typos with proper VTuber names."""
    normalized = text
    for pattern, replacement in VTUBER_NAME_REPLACEMENTS.items():
        normalized = re.sub(pattern, replacement, normalized)
    return normalized
