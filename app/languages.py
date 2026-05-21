from __future__ import annotations

import difflib
import re

# ISO 639-1 code -> canonical English name. Comprehensive enough to cover
# essentially every language a user would request. The codes double as BCP-47
# language codes for providers that need them (e.g. Google Translation LLM).
LANGUAGE_NAMES: dict[str, str] = {
    "aa": "Afar",
    "ab": "Abkhazian",
    "af": "Afrikaans",
    "ak": "Akan",
    "am": "Amharic",
    "an": "Aragonese",
    "ar": "Arabic",
    "as": "Assamese",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bm": "Bambara",
    "bn": "Bengali",
    "bo": "Tibetan",
    "br": "Breton",
    "bs": "Bosnian",
    "ca": "Catalan",
    "ce": "Chechen",
    "co": "Corsican",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "dv": "Divehi",
    "dz": "Dzongkha",
    "ee": "Ewe",
    "el": "Greek",
    "en": "English",
    "eo": "Esperanto",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "ff": "Fula",
    "fi": "Finnish",
    "fo": "Faroese",
    "fr": "French",
    "fy": "Western Frisian",
    "ga": "Irish",
    "gd": "Scottish Gaelic",
    "gl": "Galician",
    "gn": "Guarani",
    "gu": "Gujarati",
    "ha": "Hausa",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "ht": "Haitian Creole",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "ig": "Igbo",
    "is": "Icelandic",
    "it": "Italian",
    "iu": "Inuktitut",
    "ja": "Japanese",
    "jv": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "ku": "Kurdish",
    "ky": "Kyrgyz",
    "la": "Latin",
    "lb": "Luxembourgish",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mg": "Malagasy",
    "mi": "Maori",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "ne": "Nepali",
    "nl": "Dutch",
    "no": "Norwegian",
    "ny": "Nyanja",
    "oc": "Occitan",
    "om": "Oromo",
    "or": "Odia",
    "pa": "Punjabi",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "qu": "Quechua",
    "rm": "Romansh",
    "rn": "Rundi",
    "ro": "Romanian",
    "ru": "Russian",
    "rw": "Kinyarwanda",
    "sa": "Sanskrit",
    "sd": "Sindhi",
    "se": "Northern Sami",
    "sg": "Sango",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sm": "Samoan",
    "sn": "Shona",
    "so": "Somali",
    "sq": "Albanian",
    "sr": "Serbian",
    "ss": "Swati",
    "st": "Southern Sotho",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "ti": "Tigrinya",
    "tk": "Turkmen",
    "tl": "Filipino",
    "tn": "Tswana",
    "to": "Tongan",
    "tr": "Turkish",
    "ts": "Tsonga",
    "tt": "Tatar",
    "ug": "Uyghur",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "ve": "Venda",
    "vi": "Vietnamese",
    "wo": "Wolof",
    "xh": "Xhosa",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "za": "Zhuang",
    "zh": "Chinese",
    "zu": "Zulu",
}

# ISO 639-1 code -> the language's name in its own language (autonym).
LANGUAGE_NATIVE: dict[str, str] = {
    "aa": "Afar",
    "ab": "Аԥсшәа",
    "af": "Afrikaans",
    "ak": "Akan",
    "am": "አማርኛ",
    "an": "Aragonés",
    "ar": "العربية",
    "as": "অসমীয়া",
    "az": "Azərbaycan",
    "be": "Беларуская",
    "bg": "Български",
    "bm": "Bamanakan",
    "bn": "বাংলা",
    "bo": "བོད་སྐད་",
    "br": "Brezhoneg",
    "bs": "Bosanski",
    "ca": "Català",
    "ce": "Нохчийн",
    "co": "Corsu",
    "cs": "Čeština",
    "cy": "Cymraeg",
    "da": "Dansk",
    "de": "Deutsch",
    "dv": "Divehi",
    "dz": "རྫོང་ཁ",
    "ee": "Eʋegbe",
    "el": "Ελληνικά",
    "en": "English",
    "eo": "Esperanto",
    "es": "Español",
    "et": "Eesti",
    "eu": "Euskara",
    "fa": "فارسی",
    "ff": "Pulaar",
    "fi": "Suomi",
    "fo": "Føroyskt",
    "fr": "Français",
    "fy": "Frysk",
    "ga": "Gaeilge",
    "gd": "Gàidhlig",
    "gl": "Galego",
    "gn": "Avañe’ẽ",
    "gu": "ગુજરાતી",
    "ha": "Hausa",
    "he": "עברית",
    "hi": "हिन्दी",
    "hr": "Hrvatski",
    "ht": "Kreyòl Ayisyen",
    "hu": "Magyar",
    "hy": "Հայերեն",
    "id": "Bahasa Indonesia",
    "ig": "Igbo",
    "is": "Íslenska",
    "it": "Italiano",
    "iu": "Inuktitut",
    "ja": "日本語",
    "jv": "Jawa",
    "ka": "ქართული",
    "kk": "Қазақ тілі",
    "km": "ខ្មែរ",
    "kn": "ಕನ್ನಡ",
    "ko": "한국어",
    "ku": "Kurdî (kurmancî)",
    "ky": "Кыргызча",
    "la": "Lingua latina",
    "lb": "Lëtzebuergesch",
    "lo": "ລາວ",
    "lt": "Lietuvių",
    "lv": "Latviešu",
    "mg": "Malagasy",
    "mi": "Māori",
    "mk": "Македонски",
    "ml": "മലയാളം",
    "mn": "Монгол",
    "mr": "मराठी",
    "ms": "Bahasa Malaysia",
    "mt": "Malti",
    "my": "မြန်မာ",
    "ne": "नेपाली",
    "nl": "Nederlands",
    "no": "Norsk",
    "ny": "Nyanja",
    "oc": "Occitan",
    "om": "Oromoo",
    "or": "ଓଡ଼ିଆ",
    "pa": "ਪੰਜਾਬੀ",
    "pl": "Polski",
    "ps": "پښتو",
    "pt": "Português",
    "qu": "Runasimi",
    "rm": "Rumantsch",
    "rn": "Ikirundi",
    "ro": "Română",
    "ru": "Русский",
    "rw": "Ikinyarwanda",
    "sa": "संस्कृत भाषा",
    "sd": "سنڌي",
    "se": "Davvisámegiella",
    "sg": "Sängö",
    "si": "සිංහල",
    "sk": "Slovenčina",
    "sl": "Slovenščina",
    "sm": "Samoan",
    "sn": "ChiShona",
    "so": "Soomaali",
    "sq": "Shqip",
    "sr": "Српски",
    "ss": "SiSwati",
    "st": "Sesotho",
    "su": "Basa Sunda",
    "sv": "Svenska",
    "sw": "Kiswahili",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "tg": "Тоҷикӣ",
    "th": "ไทย",
    "ti": "ትግርኛ",
    "tk": "Türkmen dili",
    "tl": "Filipino",
    "tn": "Setswana",
    "to": "Lea fakatonga",
    "tr": "Türkçe",
    "ts": "Tsonga",
    "tt": "Татар",
    "ug": "ئۇيغۇرچە",
    "uk": "Українська",
    "ur": "اردو",
    "uz": "O‘zbek",
    "ve": "TshiVenḓa",
    "vi": "Tiếng Việt",
    "wo": "Wolof",
    "xh": "IsiXhosa",
    "yi": "ייִדיש",
    "yo": "Èdè Yorùbá",
    "za": "Vahcuengh",
    "zh": "中文",
    "zu": "IsiZulu",
}

# Common alternate spellings users may type for a language above.
_ALIASES: dict[str, str] = {
    "farsi": "fa",
    "mandarin": "zh",
    "castilian": "es",
    "tagalog": "tl",
    "oriya": "or",
    "myanmar": "my",
    "bangla": "bn",
    "moldovan": "ro",
    "flemish": "nl",
}

_NAME_TO_CODE: dict[str, str] = {
    name.lower(): code for code, name in LANGUAGE_NAMES.items()
}

_NATIVE_TO_CODE: dict[str, str] = {
    name.lower(): code for code, name in LANGUAGE_NATIVE.items()
}

# (searchable lowercase name, canonical English name) for every English and
# native spelling — the pool for typo suggestions.
_SEARCH_NAMES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        {(name.lower(), name) for name in LANGUAGE_NAMES.values()}
        | {
            (LANGUAGE_NATIVE[code].lower(), LANGUAGE_NAMES[code])
            for code in LANGUAGE_NATIVE
        }
    )
)

# A prefix is an alphabetic token (plus spaces/hyphens) up to 20 chars,
# followed by a colon. The body (DOTALL) keeps any further colons intact.
_PREFIX_RE = re.compile(r"^\s*([A-Za-z][A-Za-z \-]{0,19})\s*:\s*(.+)$", re.DOTALL)


def _to_code(value: str) -> str | None:
    """Resolve a code, English name, native name, or alias to a code."""
    key = value.strip().lower()
    if key in LANGUAGE_NAMES:
        return key
    if key in _NAME_TO_CODE:
        return _NAME_TO_CODE[key]
    if key in _NATIVE_TO_CODE:
        return _NATIVE_TO_CODE[key]
    return _ALIASES.get(key)


def normalize_language(value: str) -> str | None:
    """Map a code, name, or alias to the canonical English language name.

    Returns None when the value is not an exact match for a known language;
    near-misses are left for suggest_language() to handle.
    """
    code = _to_code(value)
    return LANGUAGE_NAMES[code] if code is not None else None


def to_language_code(value: str) -> str | None:
    """Map a code, name, or alias to a BCP-47 language code, or None."""
    return _to_code(value)


def native_name(value: str) -> str | None:
    """Return the language's name in its own language, or None."""
    code = _to_code(value)
    return LANGUAGE_NATIVE.get(code) if code is not None else None


def display_language(value: str) -> str:
    """Format a language for the UI: English name plus native name.

    Falls back to the English name alone when the two are identical, and to
    the raw value when it is not a recognized language.
    """
    code = _to_code(value)
    if code is None:
        return value
    english = LANGUAGE_NAMES[code]
    native = LANGUAGE_NATIVE.get(code)
    if native and native.lower() != english.lower():
        return f"{english} ({native})"
    return english


def resolve_target(value: str) -> str | None:
    """Resolve a /setlang argument to a canonical language name, or None."""
    return normalize_language(value)


def suggest_language(value: str) -> list[str]:
    """Up to 3 likely languages (English names) for a near-miss.

    Matches English and native spellings alike. Prefix matches come first (so
    a truncated word like ``Ukraini``, ``Chi`` or ``Espa`` resolves), then
    fuzzy matches catch typos such as ``Ukrannian``.
    """
    key = value.strip().lower()
    if len(key) < 2:
        return []
    out: list[str] = []
    for search, english in _SEARCH_NAMES:
        if search.startswith(key) and english not in out:
            out.append(english)
    search_map = dict(_SEARCH_NAMES)
    for match in difflib.get_close_matches(key, search_map, n=8, cutoff=0.6):
        english = search_map[match]
        if english not in out:
            out.append(english)
    return out[:3]


def parse_query(text: str) -> tuple[str | None, str]:
    """Split an optional ``lang: body`` override prefix off an inline query.

    Returns ``(target_language, body)``. ``target_language`` is None when no
    *recognized* language prefix is present; an ordinary colon in the text
    (e.g. ``Note: buy milk``) is left untouched as part of the body.
    """
    match = _PREFIX_RE.match(text)
    if match:
        candidate, body = match.group(1).strip(), match.group(2).strip()
        target = normalize_language(candidate)
        if target is not None and body:
            return target, body
    return None, text.strip()
