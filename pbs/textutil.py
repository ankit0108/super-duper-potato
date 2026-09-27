"""Text helpers shared by scouting, drafting, guardrails and learning.

The X weighted length, the edit tokenizer and the edit ratio are mirrored in the desk
(web/src/lib/text.ts). Both sides are checked against tests/vectors/*.json.
"""

from __future__ import annotations

import difflib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def normalize_ws(text: str | None) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    no_tags = _TAG_RE.sub(" ", text)
    return normalize_ws(html.unescape(no_tags))


def truncate(text: str | None, limit: int) -> str:
    text = normalize_ws(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,.;:-") + "…"


# ---------------------------------------------------------------------------
# URLs and titles
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref", "ref_src", "ref_url", "cmpid", "ocid",
    "smid", "taid", "spm", "igshid", "icid", "cid", "src", "source", "via", "trk", "xtor", "ito",
    "_hsenc", "_hsmi", "mkt_tok", "yclid", "si", "s_kwcid", "cmp", "campaign",
}


def canonical_url(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    scheme = (parts.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    query.sort()
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def url_host(url: str | None) -> str:
    try:
        host = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


_SUFFIX_SPLIT = re.compile(r"\s+(?:-|\||–|—|::)\s+")


def strip_publisher_suffix(title: str) -> str:
    """'Big news happens - The Hindu' -> 'Big news happens' (Google News style titles)."""
    title = normalize_ws(title)
    parts = _SUFFIX_SPLIT.split(title)
    if len(parts) >= 2 and len(parts[-1].split()) <= 6 and len(" ".join(parts[:-1])) >= 12:
        return " - ".join(parts[:-1])
    return title


def title_key(title: str | None) -> str:
    t = strip_publisher_suffix(title or "").casefold()
    t = "".join(ch if (_is_word_char(ch) or ch.isspace()) else " " for ch in t)
    return normalize_ws(t)


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


def devanagari_ratio(text: str | None) -> float:
    letters = [ch for ch in (text or "") if ch.isalpha()]
    if not letters:
        return 0.0
    deva = sum(1 for ch in letters if "ऀ" <= ch <= "ॿ")
    return deva / len(letters)


def detect_lang(text: str | None, default: str = "en") -> str:
    return "hi" if devanagari_ratio(text) > 0.4 else default


# ---------------------------------------------------------------------------
# Similarity tokens (clustering, dedup, novelty)
# ---------------------------------------------------------------------------

STOPWORDS_EN = frozenset(
    ["a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and", "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves", "new", "news", "says", "said", "say", "will", "just", "now", "today", "latest", "update", "updates", "report", "reports", "amid", "via", "us", "get", "gets", "got", "make", "makes", "made", "one", "two", "first", "year", "years", "week", "day", "days", "time", "times", "could", "may", "might", "like", "also", "still", "back", "know", "people", "way", "well", "even", "much", "many", "new", "top", "best"]
)

STOPWORDS_HI = frozenset(
    ["का", "के", "की", "को", "में", "से", "है", "हैं", "था", "थे", "थी", "पर", "और", "या", "एक", "यह", "वह", "ये", "वे", "इस", "उस", "इन", "उन", "तो", "भी", "ही", "लिए", "साथ", "बाद", "तक", "द्वारा", "कर", "करने", "किया", "किए", "गया", "गई", "गए", "होने", "हो", "रहा", "रही", "रहे", "जा", "जाता", "जाती", "जाते", "अब", "नहीं", "कहा", "कहते"]
)

_STEM_EXCEPTIONS = ("ss", "us", "is", "ics", "ous")


def _is_word_char(ch: str) -> bool:
    return ch == "_" or unicodedata.category(ch)[0] in ("L", "M", "N")


def _is_space(ch: str) -> bool:
    return ch in " \t\n\r\f\v" or unicodedata.category(ch) in ("Zs", "Zl", "Zp")


def _light_stem(tok: str) -> str:
    if tok.endswith("'s"):
        tok = tok[:-2]
    if len(tok) > 4 and tok.endswith("s") and not tok.endswith(_STEM_EXCEPTIONS):
        tok = tok[:-1]
    return tok


def sim_tokens(text: str | None) -> list[str]:
    """Casefolded content tokens for similarity. Keeps model names like 'gpt-5' intact."""
    text = (text or "").casefold()
    out: list[str] = []
    for raw in re.findall(r"[^\W_]+(?:[-.][^\W_]+)*", text):
        variants = [raw]
        if "-" in raw or "." in raw:
            variants += [p for p in raw.replace(".", "-").split("-") if p != raw]
        for tok in variants:
            if len(tok) < 2 or tok in STOPWORDS_EN or tok in STOPWORDS_HI:
                continue
            if tok.isdigit() and len(tok) > 4:
                continue
            out.append(_light_stem(tok))
    return out


def jaccard(a: set[str] | frozenset[str], b: set[str] | frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# X weighted length (twitter-text v3 rules, simplified; mirrored in the desk)
# ---------------------------------------------------------------------------

X_URL_LENGTH = 23
_X_URL_RE = re.compile(
    r"(?:https?://[^\s]+)|(?:\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|ai|dev|in|co|gov|edu|app|xyz|me|ly|gl|us|uk|au|news|tech|so)\b(?:/[^\s]*)?)",
    re.IGNORECASE,
)
_X_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


def _x_is_light(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _X_LIGHT_RANGES)


def _is_emoji_base(cp: int) -> bool:
    return (
        cp >= 0x1F000
        or 0x2600 <= cp <= 0x27BF
        or 0x2300 <= cp <= 0x23FF
        or 0x2B00 <= cp <= 0x2BFF
        or cp in (0x3030, 0x303D, 0x3297, 0x3299, 0x203C, 0x2049, 0x2122, 0x2139)
    )


def _is_emoji_modifier(cp: int) -> bool:
    return cp in (0xFE0F, 0xFE0E, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F


def x_weighted_length(text: str | None) -> int:
    """Weighted length as X counts it: most Latin/Devanagari chars 1, CJK and emoji 2, URLs 23."""
    text = unicodedata.normalize("NFC", text or "")
    total = 0
    pos = 0
    for m in _X_URL_RE.finditer(text):
        total += _x_segment_weight(text[pos : m.start()])
        total += X_URL_LENGTH
        pos = m.end()
    total += _x_segment_weight(text[pos:])
    return total


def _x_segment_weight(segment: str) -> int:
    cps = [ord(ch) for ch in segment]
    i, n, total = 0, len(cps), 0
    while i < n:
        cp = cps[i]
        # Regional-indicator pair (flag) counts as one emoji.
        if 0x1F1E6 <= cp <= 0x1F1FF:
            total += 2
            i += 2 if i + 1 < n and 0x1F1E6 <= cps[i + 1] <= 0x1F1FF else 1
            continue
        # Keycap: digit/#/* + FE0F? + 20E3
        if cp in (0x23, 0x2A) or 0x30 <= cp <= 0x39:
            j = i + 1
            if j < n and cps[j] == 0xFE0F:
                j += 1
            if j < n and cps[j] == 0x20E3:
                total += 2
                i = j + 1
                continue
        if _is_emoji_base(cp) or (i + 1 < n and cps[i + 1] == 0xFE0F and cp > 0x7F):
            j = i + 1
            while j < n:
                if _is_emoji_modifier(cps[j]):
                    j += 1
                elif cps[j] == 0x200D and j + 1 < n and _is_emoji_base(cps[j + 1]):
                    j += 2
                else:
                    break
            total += 2
            i = j
            continue
        total += 1 if _x_is_light(cp) else 2
        i += 1
    return total


# ---------------------------------------------------------------------------
# Edit tokens, Myers distance and edit ratio (mirrored in the desk)
# ---------------------------------------------------------------------------


def edit_tokens(text: str | None) -> list[str]:
    """Words (letters, marks, digits, underscore) and single punctuation/symbol characters."""
    tokens: list[str] = []
    buf: list[str] = []
    for ch in unicodedata.normalize("NFC", text or ""):
        if _is_word_char(ch):
            buf.append(ch)
            continue
        if buf:
            tokens.append("".join(buf))
            buf = []
        if not _is_space(ch):
            tokens.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def myers_distance(a: list[str], b: list[str]) -> int:
    """Minimum number of insertions + deletions turning a into b (Myers O((N+M)D))."""
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return n + m
    max_d = n + m
    offset = max_d
    v = [0] * (2 * max_d + 2)
    for d in range(max_d + 1):
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[offset + k - 1] < v[offset + k + 1]):
                x = v[offset + k + 1]
            else:
                x = v[offset + k - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v[offset + k] = x
            if x >= n and y >= m:
                return d
    return max_d


def edit_ratio(draft: str | None, final: str | None) -> float:
    """0.0 = posted as drafted, 1.0 = completely rewritten. Symmetric token-level measure."""
    a, b = edit_tokens(draft), edit_tokens(final)
    if not a and not b:
        return 0.0
    return round(myers_distance(a, b) / (len(a) + len(b)), 4)


def edit_changes(draft: str | None, final: str | None) -> dict[str, list[str]]:
    """Phrases removed from and added to the draft (for voice learning)."""
    a, b = edit_tokens(draft), edit_tokens(final)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace") and i2 > i1:
            removed.append(" ".join(a[i1:i2]))
        if op in ("insert", "replace") and j2 > j1:
            added.append(" ".join(b[j1:j2]))
    return {"removed": removed, "added": added}


# ---------------------------------------------------------------------------
# Sentences, numbers, openings
# ---------------------------------------------------------------------------

# A sentence ends at . ! ? or । followed by space, but not after an initial ("M. Visvesvaraya") or a
# common abbreviation ("Dr.", "e.g.").
_SENT_RE = re.compile(r"(?<![\s(][A-Z]\.)(?<!\b(?:Dr|Mr|Ms|St|vs|No)\.)(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?।])\s+|\n+")


def split_sentences(text: str | None) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text or "") if s and s.strip()]


def word_count(text: str | None) -> int:
    return sum(1 for t in edit_tokens(text) if _is_word_char(t[0]))


def opening(text: str | None, limit: int = 220) -> str:
    """The part of a post a reader sees first (first line or first sentence)."""
    text = (text or "").strip()
    first_line = text.split("\n", 1)[0].strip()
    sentences = split_sentences(first_line)
    head = sentences[0] if sentences else first_line
    return head[:limit]


_THREAD_MARK_RE = re.compile(r"(?m)^\s*(?:\d{1,2}\s*/\s*\d{0,2}|\d{1,2}[.)])\s+")
_NUMBER_RE = re.compile(
    r"(?:[$₹€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|b|million|billion|trillion|crore|lakh|cr)\b)?)"
    r"|(?:\d[\d,]*(?:\.\d+)?\s?%)"
    r"|(?:\d[\d,]*(?:\.\d+)?\s?(?:x|×|million|billion|trillion|crore|lakh|bn)\b)"
    r"|(?:\b\d[\d,]*\.\d+\b)"
    r"|(?:\b\d{1,3}(?:,\d{2})+,\d{3}\b)"
    r"|(?:\b\d{1,3}(?:,\d{3})+\b)"
    r"|(?:\b\d{2,}\b)",
    re.IGNORECASE,
)


def numeric_claims(text: str | None) -> list[str]:
    """Figures, percentages, amounts and years that a source should back up."""
    cleaned = _THREAD_MARK_RE.sub(" ", text or "")
    found: list[str] = []
    for m in _NUMBER_RE.finditer(cleaned):
        token = m.group(0).strip()
        if token not in found:
            found.append(token)
    return found


def number_core(token: str) -> str:
    """'₹2,000 crore' -> '2000'; '37%' -> '37'; '3.5x' -> '3.5'."""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", token)
    return m.group(0).replace(",", "") if m else token


def normalize_numbers(text: str | None) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", text or "")
