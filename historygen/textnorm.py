"""Text normalisation applied to narration before TTS.

ElevenLabs mispronounces Roman numerals ("II. Mehmed", "Louis XIV", "XX. yüzyıl"),
so they are expanded to ordinal words in the narration language. Only the spoken
text is normalised — on_screen_text keeps Roman numerals for display, and captions
follow the spoken form automatically because they are built from the TTS alignment.

Supported languages: tr, az (numeral-first, "II. Mehmed" → "İkinci Mehmed") and
en (numeral-after-name, "Mehmed II" → "Mehmed the Second"). Other languages pass
through unchanged.
"""

from __future__ import annotations

import re

# Strict form only — rejects things like "IIII" so stray letter runs aren't numbers.
_VALID_ROMAN = re.compile(r"^(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

_UNIT_ORDINALS = {
    "tr": ["", "birinci", "ikinci", "üçüncü", "dördüncü", "beşinci",
           "altıncı", "yedinci", "sekizinci", "dokuzuncu"],
    "az": ["", "birinci", "ikinci", "üçüncü", "dördüncü", "beşinci",
           "altıncı", "yeddinci", "səkkizinci", "doqquzuncu"],
    "en": ["", "first", "second", "third", "fourth", "fifth",
           "sixth", "seventh", "eighth", "ninth"],
}
_TENS_ORDINALS = {
    "tr": ["", "onuncu", "yirminci", "otuzuncu", "kırkıncı", "ellinci",
           "altmışıncı", "yetmişinci", "sekseninci", "doksanıncı"],
    "az": ["", "onuncu", "iyirminci", "otuzuncu", "qırxıncı", "əllinci",
           "altmışıncı", "yetmişinci", "səksəninci", "doxsanıncı"],
    "en": ["", "tenth", "twentieth", "thirtieth", "fortieth", "fiftieth",
           "sixtieth", "seventieth", "eightieth", "ninetieth"],
}
_TENS_CARDINALS = {
    "tr": ["", "on", "yirmi", "otuz", "kırk", "elli",
           "altmış", "yetmiş", "seksen", "doksan"],
    "az": ["", "on", "iyirmi", "otuz", "qırx", "əlli",
           "altmış", "yetmiş", "səksən", "doxsan"],
    "en": ["", "ten", "twenty", "thirty", "forty", "fifty",
           "sixty", "seventy", "eighty", "ninety"],
}
_EN_TEEN_ORDINALS = ["tenth", "eleventh", "twelfth", "thirteenth", "fourteenth",
                     "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth"]
# "World War II" reads as a cardinal ("Two"), not "the Second".
_EN_CARDINALS = ["", "one", "two", "three", "four", "five",
                 "six", "seven", "eight", "nine", "ten"]
# Names where a trailing "X" is part of the name, not a numeral.
_EN_X_NAMES = {"Malcolm"}

# Numeral-first with a period: "II. Mehmed", "XX. yüzyıl". The lookahead captures
# the first letter of the next word to match its capitalisation.
_NUMERAL_FIRST = re.compile(r"\b([IVXLC]+)\.(?=\s+(\S))")
# Numeral after a name: "Mehmed II", "Louis XIV". The name must be a normal
# capitalised word (not an acronym like WWII).
_NUMERAL_AFTER = re.compile(r"\b([A-Z][a-z]+)\s+([IVXLC]+)\b")


def _roman_to_int(s: str) -> int | None:
    if not _VALID_ROMAN.match(s):
        return None
    total = 0
    for i, ch in enumerate(s):
        v = _ROMAN_VALUES[ch]
        total += -v if i + 1 < len(s) and _ROMAN_VALUES[s[i + 1]] > v else v
    return total if 1 <= total <= 99 else None


def _ordinal(n: int, lang: str) -> str:
    tens, unit = divmod(n, 10)
    if lang == "en" and 10 <= n <= 19:
        return _EN_TEEN_ORDINALS[n - 10]
    if unit == 0:
        return _TENS_ORDINALS[lang][tens]
    if tens == 0:
        return _UNIT_ORDINALS[lang][unit]
    joiner = "-" if lang == "en" else " "
    return _TENS_CARDINALS[lang][tens] + joiner + _UNIT_ORDINALS[lang][unit]


def _capitalize(word: str, lang: str) -> str:
    # Turkish/Azerbaijani dotted capital: ikinci → İkinci, iyirmi → İyirmi.
    if lang in ("tr", "az") and word[0] == "i":
        return "İ" + word[1:]
    return word[0].upper() + word[1:]


def expand_roman_numerals(text: str, language: str) -> str:
    """Rewrite Roman numerals in `text` as ordinal words in `language`."""
    if language in ("tr", "az"):
        def repl(m: re.Match) -> str:
            n = _roman_to_int(m.group(1))
            if n is None:
                return m.group(0)
            word = _ordinal(n, language)
            return _capitalize(word, language) if m.group(2).isupper() else word

        return _NUMERAL_FIRST.sub(repl, text)

    if language == "en":
        def repl(m: re.Match) -> str:
            name, numeral = m.group(1), m.group(2)
            n = _roman_to_int(numeral)
            if n is None or (numeral == "X" and name in _EN_X_NAMES):
                return m.group(0)
            if name == "War" and n < len(_EN_CARDINALS):
                return f"{name} {_EN_CARDINALS[n].capitalize()}"
            return f"{name} the {_ordinal(n, 'en').capitalize()}"

        return _NUMERAL_AFTER.sub(repl, text)

    return text
