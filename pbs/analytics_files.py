"""Analytics exports, read exactly: LinkedIn's .xlsx (content or a single post's analytics) and X's .csv.

Numbers come straight from the cells, no model reading them. The layouts change now and then, so nothing
depends on a sheet's name or position: header rows are found by their column names (in several wordings),
and what's under them is read as one of
- posts: a row per post (a URL, an id or the text, a date, and numbers), several tables side by side allowed
  (LinkedIn's "Top posts" sheet has one table by engagements next to one by impressions);
- one post: label and value pairs down two columns (LinkedIn's export of a single post);
- days: a date and numbers per row (impressions, engagements, new followers a day);
- audience: the top job titles, industries, locations... with their share;
- followers: "Total followers on <date>: <n>".
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import textutil

FILE_SUFFIXES = (".xlsx", ".csv")
MAX_ROWS = 5000
MAX_COLS = 40

# Column wordings in LinkedIn's and X's exports (old and new), lowercased without punctuation.
COLUMNS: dict[str, tuple[str, ...]] = {
    "url": ("post url", "post link", "tweet permalink", "permalink", "url", "link", "post permalink"),
    "id": ("post id", "tweet id"),
    "date": ("post publish date", "post date", "publish date", "date", "time", "created at", "posted at", "published"),
    "text": ("post text", "tweet text", "text", "post title", "post content", "content", "commentary"),
    "impressions": ("impressions", "views", "post impressions", "impression"),
    "members_reached": ("members reached", "unique impressions", "reach"),
    "reactions": ("reactions", "likes"),
    "comments": ("comments", "replies"),
    "reposts": ("reposts", "retweets"),
    "sends": ("sends", "sends on linkedin", "shares"),
    "saves": ("saves", "bookmarks"),
    "followers_gained": ("followers gained from this post", "followers gained", "new follows", "follows",
                         "new followers"),
    "profile_views": ("profile viewers from this post", "profile visits", "user profile clicks", "profile views"),
    "link_clicks": ("link clicks", "url clicks", "link engagements", "clicks"),
    "engagements": ("engagements", "total engagements"),
}
METRICS = ("impressions", "members_reached", "reactions", "comments", "reposts", "sends", "saves", "followers_gained",
           "profile_views", "link_clicks", "engagements")
POST_KEYS = ("url", "id", "text")
_ALIAS = {w: k for k, words in COLUMNS.items() for w in words}


def _norm(cell: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(cell or "").lower())).strip()


# Words a header may add after a known name ("Impressions (total)", "Reactions count").
_QUALIFIERS = {"total", "totals", "organic", "count", "all", "num", "number", "sum"}


def column(cell: Any) -> str | None:
    """The field a header cell names, if any."""
    n = _norm(cell)
    if not n:
        return None
    if n in _ALIAS:
        return _ALIAS[n]
    words = n.split()
    for cut in range(len(words) - 1, 0, -1):
        head, rest = " ".join(words[:cut]), words[cut:]
        if head in _ALIAS and all(w in _QUALIFIERS for w in rest):
            return _ALIAS[head]
    return None


def _is_header(row: list[Any]) -> bool:
    """A row of column names: two or more known names, and no numbers or links among its cells."""
    named = sum(1 for c in row if column(c))
    if named < 2:
        return False
    for c in row:
        if isinstance(c, (int, float, dt.date)) and not isinstance(c, bool):
            return False
        s = str(c or "").strip()
        if s.startswith(("http://", "https://")) or (s and number(s) is not None):
            return False
    return True


def number(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().lower().replace(",", "").replace(" ", "").replace(" ", "")
    if not s or s in ("-", "--", "n/a"):
        return None
    mult = 1
    if s.endswith("k"):
        mult, s = 1000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    if s.endswith("%"):
        return None
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%a, %b %d, %Y",
                 "%b %d, %Y", "%d %b %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M")


def date(v: Any) -> str | None:
    """A YYYY-MM-DD date from a cell (a date, a datetime, or text in the usual formats)."""
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v or "").strip()
    if not s:
        return None
    s = re.sub(r"(\+\d{2}:?\d{2}|Z| UTC)$", "", s).strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def post_key(url: str | None) -> str | None:
    """The post's own id in a LinkedIn or X link (activity or share number; status number), to match links in
    different shapes (/feed/update/urn:li:activity:…, /posts/name_slug-activity-…, x.com or twitter.com)."""
    if not url:
        return None
    m = re.search(r"(?:activity|share|ugcPost)[:\-](\d{15,22})", url) or re.search(r"/status(?:es)?/(\d{6,22})", url)
    return m.group(1) if m else None


def platform_of(url: str | None) -> str | None:
    host = textutil.url_host(url or "")
    if host.endswith("linkedin.com") or host == "lnkd.in":
        return "linkedin"
    if host in ("x.com", "twitter.com", "mobile.twitter.com"):
        return "x"
    return None


@dataclass
class PostRow:
    platform: str | None
    url: str | None = None
    post_id: str | None = None
    date: str | None = None
    text: str | None = None
    values: dict[str, int] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return post_key(self.url) or self.post_id or f"{self.date}:{textutil.title_key(self.text or '')[:40]}"


@dataclass
class Parsed:
    platform: str | None = None
    posts: list[PostRow] = field(default_factory=list)
    days: dict[str, dict[str, int]] = field(default_factory=dict)
    audience: list[dict[str, Any]] = field(default_factory=list)
    followers: tuple[str, int] | None = None
    totals: dict[str, int] = field(default_factory=dict)
    period: str | None = None
    sheets: int = 0

    def summary(self) -> dict[str, Any]:
        return {"platform": self.platform, "posts": len(self.posts), "days": len(self.days),
                "audience": len(self.audience), "followers": self.followers[1] if self.followers else None,
                "totals": bool(self.totals)}

    @property
    def empty(self) -> bool:
        return not (self.posts or self.days or self.audience or self.followers or self.totals)


def read_tables(path: Path) -> list[tuple[str, list[list[Any]]]]:
    """Every sheet (an .xlsx) or the one table (a .csv), as rows of cells."""
    if path.suffix.lower() == ".csv":
        raw = path.read_bytes()
        text = next((raw.decode(enc) for enc in ("utf-8-sig", "utf-16") if _decodes(raw, enc)), raw.decode("latin-1"))
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = [r[:MAX_COLS] for r in itertools.islice(csv.reader(io.StringIO(text), dialect), MAX_ROWS)]
        return [(path.stem, rows)]
    import openpyxl  # only needed for spreadsheets

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        out = []
        for sheet in book.worksheets:
            rows = [list(r[:MAX_COLS]) for r in itertools.islice(sheet.iter_rows(values_only=True), MAX_ROWS)]
            out.append((sheet.title, rows))
        return out
    finally:
        book.close()


def _decodes(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def parse(path: Path, hint: str | None = None) -> Parsed:
    """Everything an export holds. `hint`: the platform when nothing in the file says (from the upload)."""
    out = Parsed()
    for name, rows in read_tables(path):
        out.sheets += 1
        _parse_sheet(name, rows, out)
    out.platform = _platform(path, out, hint)
    for p in out.posts:
        p.platform = p.platform or out.platform
    return out


def _platform(path: Path, out: Parsed, hint: str | None) -> str | None:
    """The links in it, else the file's name, else what the upload said, else the kind of file: LinkedIn exports
    spreadsheets and X exports CSV."""
    seen = {p.platform for p in out.posts if p.platform}
    if len(seen) == 1:
        return seen.pop()
    name = path.name.lower()
    if "linkedin" in name:
        return "linkedin"
    if "tweet" in name or "account_analytics" in name or "account_overview" in name:
        return "x"
    if hint in ("linkedin", "x"):
        return hint
    return "linkedin" if path.suffix.lower() == ".xlsx" else "x"


def _parse_sheet(name: str, rows: list[list[Any]], out: Parsed) -> None:
    _followers(rows, out)
    if _audience(name, rows, out):
        return
    tables = 0
    i = 0
    while i < len(rows):
        if _is_header(rows[i]):
            cols = [column(c) for c in rows[i]]
            if any(c in METRICS for c in cols) and (any(c in POST_KEYS for c in cols) or "date" in cols):
                i = _table(rows, i, cols, out)
                tables += 1
                continue
        i += 1
    if not tables:
        _pairs(rows, out)


def _segments(cols: list[str | None]) -> list[list[int]]:
    """Columns of each table in a header row: a new table starts at each repeated post key (side by side)."""
    segments: list[list[int]] = [[]]
    seen: set[str] = set()
    for j, c in enumerate(cols):
        if c is None:
            continue
        if c in seen:
            if c not in (*POST_KEYS, "date"):
                continue  # a second column for the same number: the first one counts
            segments.append([])
            seen = set()
        seen.add(c)
        segments[-1].append(j)
    return [s for s in segments if s]


def _table(rows: list[list[Any]], start: int, cols: list[str | None], out: Parsed) -> int:
    """Rows under a header, until a blank row or the next header. Returns where it stopped."""
    end = start + 1
    while end < len(rows) and any(str(c or "").strip() for c in rows[end]) and not _is_header(rows[end]):
        end += 1
    for seg in _segments(cols):
        names = {cols[j]: j for j in seg}
        is_posts = any(k in names for k in POST_KEYS)
        for r in rows[start + 1:end]:
            def cell(k: str, r: list[Any] = r, names: dict[str | None, int] = names) -> Any:
                return r[names[k]] if k in names and names[k] < len(r) else None

            values = {k: n for k in METRICS if k in names and (n := number(cell(k))) is not None}
            if not values:
                continue
            day = date(cell("date"))
            if is_posts:
                url = str(cell("url") or "").strip() or None
                url = url if url and url.startswith(("http://", "https://")) else None
                text = textutil.normalize_ws(str(cell("text") or "")) or None
                pid = str(cell("id") or "").strip() or None
                if not (url or text or pid):
                    continue
                _merge(out, PostRow(platform_of(url), url, pid, day, text, values))
            elif day:
                bucket = out.days.setdefault(day, {})
                for k, v in values.items():
                    bucket[k] = max(bucket.get(k, 0), v)
    return end


def _merge(out: Parsed, row: PostRow) -> None:
    for p in out.posts:
        if p.key == row.key:
            p.values.update(row.values)
            p.url, p.date, p.text, p.post_id = p.url or row.url, p.date or row.date, p.text or row.text, p.post_id or row.post_id
            p.platform = p.platform or row.platform
            return
    out.posts.append(row)


def _pairs(rows: list[list[Any]], out: Parsed) -> None:
    """A sheet of label/value pairs: one post's analytics (LinkedIn's export of a single post) when it names the
    post's link, else the period's totals ("Overall performance": impressions, members reached)."""
    found: dict[str, Any] = {}
    for r in rows:
        if len(r) >= 2 and (k := column(r[0])) and k not in found and r[1] not in (None, ""):
            found[k] = r[1]
        elif len(r) >= 2 and _norm(r[0]).startswith("overall performance") and r[1]:
            out.period = textutil.normalize_ws(str(r[1]))[:40]
    values = {k: n for k in METRICS if k in found and (n := number(found[k])) is not None}
    if not values:
        return
    url = str(found.get("url") or "").strip()
    if url.startswith(("http://", "https://")):
        _merge(out, PostRow(platform_of(url), url, None, date(found.get("date")), None, values))
    else:
        out.totals.update(values)


_FOLLOWERS = re.compile(r"total followers(?: on ([\d/.\-]+|\w+ \d{1,2},? \d{4}))?\s*:?\s*([\d,]+)\b", re.I)


def _followers(rows: list[list[Any]], out: Parsed) -> None:
    for r in rows[:12]:
        line = " ".join(str(c) for c in r if c not in (None, ""))
        m = _FOLLOWERS.search(line)
        if m and (n := number(m.group(2))) is not None:
            out.followers = (date(m.group(1)) or "", n)
            return


def _audience(name: str, rows: list[list[Any]], out: Parsed) -> bool:
    """LinkedIn's demographics: rows of category, value and share."""
    for i, r in enumerate(rows[:5]):
        heads = [_norm(c) for c in r]
        if any("demographic" in h for h in heads) and any("percent" in h for h in heads):
            cat, val, pct = 0, 1, next(j for j, h in enumerate(heads) if "percent" in h)
            for row in rows[i + 1:i + 200]:
                if len(row) > pct and row[cat] and row[val]:
                    share = row[pct]
                    try:
                        share = round(float(str(share).rstrip("%")) * (1 if "%" in str(share) else 100), 1)
                    except ValueError:
                        share = None
                    out.audience.append({"category": textutil.normalize_ws(str(row[cat]))[:60],
                                         "value": textutil.normalize_ws(str(row[val]))[:80], "share": share})
            return True
    return False
