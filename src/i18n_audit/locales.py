"""Locale code recognition."""
from __future__ import annotations

import re
from typing import Iterable, Optional

# ISO 639-1 plus the ISO 639-2/3 codes that show up in real catalogs.
LANGUAGES = set("""
aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz
ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik
io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml
mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd
se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi
vo wa wo xh yi yo za zh zu
ast bal bar bem ber bho brx byn ceb chr ckb cop crh csb dsb ewo fil fur gsw hak haw hsb ilo jbo kab kmr
kok lij lkt lmo ltg mai mfe mni nah nan nap nds nso oci pap pcm rue sah sat scn sco sma smj sms szl tlh
tok tzm vec yue zgh
""".split())

_LOCALE = re.compile(
    r"^(?P<lang>[A-Za-z]{2,3})"
    r"(?:[-_](?P<script>[A-Z][a-z]{3}|[a-z]{4}))?"
    r"(?:[-_](?P<region>[A-Za-z]{2}|\d{3}))?"
    r"(?:[-_@](?P<variant>[A-Za-z0-9]{4,8}))?$"
)


def parse(code: str) -> Optional[str]:
    """Return a normalized BCP 47-ish tag if ``code`` looks like a locale, else None."""
    m = _LOCALE.match(code)
    if not m or m.group("lang").lower() not in LANGUAGES:
        return None
    # a two letter all-caps "region" alone (e.g. "IT") is too ambiguous, require lowercase language
    if m.group("lang") != m.group("lang").lower() and len(code) <= 3:
        return None
    return code


def android_qualifier(q: str) -> Optional[str]:
    """``values-pt-rBR`` -> ``pt-BR``; ``values-b+sr+Latn`` -> ``sr-Latn``; ``values-night`` -> None."""
    if q.startswith("b+"):
        parts = q[2:].split("+")
        return "-".join(parts) if parts[0] in LANGUAGES else None
    parts = q.split("-")
    if parts[0] not in LANGUAGES:
        return None
    out = [parts[0]]
    if len(parts) > 1 and re.fullmatch(r"r[A-Z]{2}", parts[1]):
        out.append(parts[1][1:])
    return "-".join(out)


def norm(code: str) -> str:
    return code.replace("_", "-").lower()


def matches_source(code: str, source: str) -> bool:
    c, s = norm(code), norm(source)
    return c == s or c.startswith(s + "-")


def pick_source(codes: Iterable[str], source: str) -> Optional[str]:
    """Choose the source locale among ``codes``: exact match, then en-US style, then any variant."""
    codes = sorted(codes)
    for c in codes:
        if norm(c) == norm(source):
            return c
    preferred = {"en": "en-us", "pt": "pt-br", "zh": "zh-cn", "es": "es-es", "fr": "fr-fr", "de": "de-de"}
    want = preferred.get(norm(source))
    for c in codes:
        if want and norm(c) == want:
            return c
    for c in codes:
        if matches_source(c, source):
            return c
    return None
