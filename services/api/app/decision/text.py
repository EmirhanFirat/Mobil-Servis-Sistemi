"""Türkçe metin normalleştirme: büyük/küçük harf ve aksan katlama, kelimelere bölme."""

import re

_FOLD = str.maketrans("çğıöşü", "cgiosu")
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def normalize(text: str) -> str:
    """Küçük harfe çevirir (Türkçe İ/I kurallarıyla), aksanları katlar, boşlukları sadeleştirir.

    "Kıvılcım" ve "kivilcim" aynı forma gelir; böylece Türkçe karakter kullanmayan yazım
    da eşleşir. Yazım hatalarını düzeltmez (kuralların bilinen zayıflığı).
    """
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    return " ".join(lowered.translate(_FOLD).split())


def words(normalized: str) -> list[str]:
    return _WORD.findall(normalized)


def has_stem(tokens: list[str], stems: tuple[str, ...]) -> list[str]:
    """Kelimelerden önek olarak eşleşen kökleri döndürür (Türkçe ekler için: priz → prizden)."""
    return [stem for stem in stems if any(token.startswith(stem) for token in tokens)]
