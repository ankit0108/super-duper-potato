"""AI images for visuals: an illustration for a post, or a background for a carousel cover, big number or quote
card.

The image model never draws words: the desk lays every word over the picture, so the text stays exact and is
checked like a draft. Providers, tried in the order set in settings (images.providers), each only when its
secrets are set:

- cloudflare: Workers AI (FLUX), free within a daily allowance. CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN.
- gemini_image: Gemini's image models, paid per image (no free quota). GEMINI_IMAGE_API_KEY.
- xai: Grok Imagine, paid per image. XAI_API_KEY.

Every attempt is a row in the `images` table (today's usage, errors and the file). Files go to media/ai/<card>/
in the data repo; learn.prune removes the ones nothing needs any more. Logs carry provider, model, size and timing,
never the prompt.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import re
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from . import guardrails, ids, log, timeutil
from .context import Ctx

MEDIA_DIR = "media/ai"  # its own folder: media/metrics holds his analytics screenshots, which prune never touches
MAX_BYTES = 6_000_000
CF_API = "https://api.cloudflare.com/client/v4"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
XAI_API = "https://api.x.ai/v1"
NO_WORDS = ("No text, letters, numbers, captions, labels, logos, watermarks or signatures anywhere in the image. "
            "No real people and no recognisable faces.")
SETUP_HINT = "add the CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN secrets (free; docs/SETUP.md, AI images)"


class ImageError(Exception):
    """A provider couldn't make the image. `quota`: its allowance is used up for today. `fatal`: retrying can't
    help today (bad key, no access). `code` is the provider's error code, safe for public logs."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None, quota: bool = False,
                 retryable: bool = False, fatal: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code if code and re.fullmatch(r"[A-Za-z0-9_.\-]{1,48}", code) else None
        self.quota = quota
        self.retryable = retryable
        self.fatal = fatal

    def public(self) -> str:
        kind = ("daily allowance used up" if self.quota else "key rejected" if self.status in (401, 403)
                else "server error" if (self.status or 0) >= 500 else "network error" if self.code == "network"
                else "request failed")
        detail = " ".join(p for p in (f"HTTP {self.status}" if self.status else "", self.code or "") if p)
        return f"{kind} ({detail})" if detail else kind


class ImagesUnavailable(Exception):
    """No provider can make an image now: none is set up, images are off, or today's limit is reached."""


@dataclass
class ImageResult:
    data: bytes
    content_type: str
    width: int
    height: int
    provider: str
    model: str
    ms: int = 0
    path: str = ""  # where generate() saved it, relative to the data root


# --- bytes ------------------------------------------------------------------------------------------------------

def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def dimensions(data: bytes) -> tuple[int, int] | None:
    """Width and height from a PNG, JPEG or WebP header (None if it can't tell)."""
    kind = sniff(data)
    try:
        if kind == "image/png":
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
        if kind == "image/jpeg":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                size = struct.unpack(">H", data[i + 2:i + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return int(w), int(h)
                i += 2 + size
        if kind == "image/webp":
            chunk = data[12:16]
            if chunk == b"VP8X":
                return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return int(w & 0x3FFF), int(h & 0x3FFF)
            if chunk == b"VP8L":
                b = int.from_bytes(data[21:25], "little")
                return 1 + (b & 0x3FFF), 1 + ((b >> 14) & 0x3FFF)
    except (struct.error, IndexError):
        return None
    return None


def _decode(b64: str) -> bytes:
    try:
        return base64.b64decode(b64, validate=False)
    except (ValueError, TypeError) as exc:
        raise ImageError("the reply's image couldn't be decoded", code="bad_body") from exc


def _result(data: bytes, provider: str, model: str, w: int, h: int, ms: int) -> ImageResult:
    kind = sniff(data)
    if not kind:
        raise ImageError("the reply wasn't an image", code="bad_body")
    if len(data) > MAX_BYTES:
        raise ImageError(f"the image is too large ({len(data)} bytes)", code="too_large")
    real = dimensions(data) or (w, h)
    return ImageResult(data=data, content_type=kind, width=real[0], height=real[1], provider=provider, model=model,
                       ms=ms)


def demo_png(seed: str, width: int = 160, height: int = 200) -> bytes:
    """A small, deterministic abstract picture (soft gradient and a sun-like disc): the demo's and the tests'
    stand-in for a real image model. Pure Python: no imaging library needed."""
    h = zlib.crc32(seed.encode("utf-8"))
    base = [(h >> s) & 0xFF for s in (0, 8, 16)]
    top = [60 + c * 140 // 255 for c in base]
    bottom = [20 + c * 60 // 255 for c in reversed(base)]
    cx, cy, rad = width * (0.3 + (h % 40) / 100), height * 0.38, min(width, height) * 0.22
    rows = []
    for y in range(height):
        t = y / max(1, height - 1)
        row = bytearray([0])
        for x in range(width):
            px = [round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)]
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d < rad:
                glow = 1 - d / rad * 0.35
                px = [min(255, round(v * 0.25 + 235 * glow * 0.75)) for v in px]
            row += bytes(px)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# --- providers --------------------------------------------------------------------------------------------------

def _classify(resp: httpx.Response, body: Any) -> ImageError:
    code = None
    message = ""
    if isinstance(body, dict):
        errs = body.get("errors") or ([body["error"]] if isinstance(body.get("error"), dict) else [])
        if errs and isinstance(errs[0], dict):
            code = str(errs[0].get("code") or errs[0].get("status") or "") or None
            message = str(errs[0].get("message") or "")
        elif isinstance(body.get("error"), str):
            message = body["error"]
    status = resp.status_code
    text = message.lower()
    quota = status == 429 and ("quota" in text or "limit" in text or "allocation" in text or "credit" in text) \
        or code == "4006" or "daily free allocation" in text or "insufficient" in text and "credit" in text
    return ImageError(f"HTTP {status}: {message[:200]}", status=status, code=code, quota=quota,
                      retryable=status == 429 and not quota or status >= 500,
                      fatal=status in (401, 403) or (status == 402))


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


class Cloudflare:
    """Workers AI. FLUX.2 [klein] takes multipart form fields (prompt, width, height); FLUX.1 [schnell] takes
    JSON and makes 1024×1024. Both answer {"result": {"image": <base64>}}."""

    name = "cloudflare"

    def __init__(self, models: list[str]):
        self.models = models

    def available(self) -> bool:
        return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip() and os.environ.get("CLOUDFLARE_API_TOKEN", "").strip())

    def generate(self, client: httpx.Client, prompt: str, width: int, height: int) -> ImageResult:
        last: ImageError | None = None
        for model in self.models:
            try:
                return self._run(client, model, prompt, width, height)
            except ImageError as exc:
                last = exc
                if exc.quota or exc.fatal:
                    raise
                log.info(f"images: cloudflare {model}: {exc.public()}; trying the next model")
        raise last or ImageError("no Cloudflare model configured", code="no_model")

    def _run(self, client: httpx.Client, model: str, prompt: str, width: int, height: int) -> ImageResult:
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
        url = f"{CF_API}/accounts/{account}/ai/run/{model}"
        headers = {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN'].strip()}"}
        start = time.monotonic()
        try:
            if "flux-2" in model:
                resp = client.post(url, headers=headers, files={"prompt": (None, prompt), "width": (None, str(width)),
                                                                "height": (None, str(height))})
            else:
                resp = client.post(url, headers=headers, json={"prompt": prompt, "steps": 4})
        except httpx.HTTPError as exc:
            raise ImageError(f"network error: {type(exc).__name__}", code="network", retryable=True) from exc
        ms = int((time.monotonic() - start) * 1000)
        if resp.headers.get("content-type", "").startswith("image/") and resp.status_code == 200:
            return _result(resp.content, self.name, model, width, height, ms)
        body = _json(resp)
        if resp.status_code != 200 or not isinstance(body, dict) or body.get("success") is False:
            raise _classify(resp, body)
        image = (body.get("result") or {}).get("image") if isinstance(body.get("result"), dict) else None
        if not isinstance(image, str) or not image:
            raise ImageError("no image in the reply", code="bad_body")
        return _result(_decode(image), self.name, model, width, height, ms)


class GeminiImage:
    """Gemini's image models (Nano Banana): generateContent with responseModalities IMAGE. Paid per image."""

    name = "gemini_image"

    def __init__(self, models: list[str]):
        self.models = models

    def available(self) -> bool:
        return bool(os.environ.get("GEMINI_IMAGE_API_KEY", "").strip())

    def generate(self, client: httpx.Client, prompt: str, width: int, height: int) -> ImageResult:
        ratio = "4:5" if height > width else "16:9" if width > height * 1.4 else "1:1"
        last: ImageError | None = None
        for model in self.models:
            body = {"contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}}}
            start = time.monotonic()
            try:
                resp = client.post(f"{GEMINI_API}/models/{model}:generateContent", json=body,
                                   headers={"x-goog-api-key": os.environ["GEMINI_IMAGE_API_KEY"].strip()})
            except httpx.HTTPError as exc:
                raise ImageError(f"network error: {type(exc).__name__}", code="network", retryable=True) from exc
            data = _json(resp)
            if resp.status_code == 404:
                last = ImageError("model not available", status=404, code="NOT_FOUND")
                continue
            if resp.status_code != 200:
                err = _classify(resp, data)
                text = str(data)[:2000].lower() if data is not None else ""
                if resp.status_code == 429 and ("limit: 0" in text or "free_tier" in text or "free tier" in text):
                    err = ImageError("no image quota on this key: Gemini images need billing on its project",
                                     status=429, code="no_free_tier", quota=True)
                raise err
            for cand in (data or {}).get("candidates") or []:
                for part in ((cand or {}).get("content") or {}).get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data") if isinstance(part, dict) else None
                    if isinstance(inline, dict) and inline.get("data"):
                        return _result(_decode(inline["data"]), self.name, model, width, height,
                                       int((time.monotonic() - start) * 1000))
            last = ImageError("no image in the reply (the model may have declined the prompt)", code="no_image")
        raise last or ImageError("no Gemini image model configured", code="no_model")


class XaiImage:
    """Grok Imagine through xAI's OpenAI-style images endpoint. Paid per image."""

    name = "xai"

    def __init__(self, model: str):
        self.model = model

    def available(self) -> bool:
        return bool(os.environ.get("XAI_API_KEY", "").strip())

    def generate(self, client: httpx.Client, prompt: str, width: int, height: int) -> ImageResult:
        start = time.monotonic()
        try:
            resp = client.post(f"{XAI_API}/images/generations",
                               headers={"Authorization": f"Bearer {os.environ['XAI_API_KEY'].strip()}"},
                               json={"model": self.model, "prompt": prompt, "n": 1, "response_format": "b64_json"})
        except httpx.HTTPError as exc:
            raise ImageError(f"network error: {type(exc).__name__}", code="network", retryable=True) from exc
        data = _json(resp)
        if resp.status_code != 200:
            raise _classify(resp, data)
        item = ((data or {}).get("data") or [None])[0] or {}
        if item.get("b64_json"):
            return _result(_decode(item["b64_json"]), self.name, self.model, width, height,
                           int((time.monotonic() - start) * 1000))
        if item.get("url"):
            try:
                got = client.get(item["url"])
            except httpx.HTTPError as exc:
                raise ImageError(f"network error: {type(exc).__name__}", code="network", retryable=True) from exc
            if got.status_code == 200:
                return _result(got.content, self.name, self.model, width, height, int((time.monotonic() - start) * 1000))
        raise ImageError("no image in the reply", code="bad_body")


def providers(ctx: Ctx) -> list[Any]:
    s = ctx.settings.images
    made = {"cloudflare": Cloudflare(s.cloudflare_models), "gemini_image": GeminiImage(s.gemini_models),
            "xai": XaiImage(s.xai_model)}
    return [made[n] for n in s.providers if n in made]


# --- the chain --------------------------------------------------------------------------------------------------

def _today() -> str:
    return timeutil.now().strftime("%Y-%m-%d")


def used_today(ctx: Ctx) -> int:
    return ctx.store.count("images", "day = ? AND status = 'ok'", (_today(),))


def _out_today(ctx: Ctx, provider: str) -> bool:
    return ctx.store.count("images", "day = ? AND provider = ? AND status IN ('quota', 'fatal')",
                           (_today(), provider)) > 0


def configured(ctx: Ctx) -> list[str]:
    """Providers with their secrets set, in order (whether or not they have allowance left today)."""
    return [p.name for p in providers(ctx) if p.available()] if ctx.settings.images.enabled else []


def status(ctx: Ctx) -> dict[str, Any]:
    """For the desk: can it offer AI images now, and today's use."""
    names = configured(ctx)
    errors = ctx.store.select("images", "day = ? AND status != 'ok'", (_today(),), order="created_at DESC", limit=1)
    used = used_today(ctx)
    limit = ctx.settings.images.daily_limit
    usable = [n for n in names if not _out_today(ctx, n)]
    return {"available": bool(usable) and used < limit, "providers": names, "used_today": used, "daily_limit": limit,
            "last_error": f"{errors[0]['provider']}: {errors[0]['error']}" if errors else None}


def record(ctx: Ctx, provider: str, card_id: str | None, purpose: str, *, result: ImageResult | None = None,
            path: str | None = None, error: ImageError | None = None) -> None:
    row: dict[str, Any] = {"id": ids.new_id("img"), "day": _today(), "provider": provider, "card_id": card_id,
                           "purpose": purpose, "created_at": timeutil.now_iso()}
    if result is not None:
        row.update(model=result.model, path=path, content_type=result.content_type, bytes=len(result.data),
                   width=result.width, height=result.height, ms=result.ms, status="ok")
    else:
        assert error is not None
        row.update(status="quota" if error.quota else "fatal" if error.fatal else "failed", error=error.public())
    ctx.store.insert("images", row)


def client_for(ctx: Ctx) -> httpx.Client:
    return httpx.Client(timeout=120, transport=ctx.transport) if ctx.transport is not None else httpx.Client(timeout=120)


def generate(ctx: Ctx, prompt: str, width: int, height: int, *, card_id: str | None = None,
             purpose: str = "image") -> ImageResult:
    """One image from the first provider that can make it. Raises ImagesUnavailable when none can today (set
    up, allowance, the daily limit), ImageError when they were tried and failed (worth retrying later)."""
    if not ctx.settings.images.enabled:
        raise ImagesUnavailable("AI images are turned off in Settings")
    chain = [p for p in providers(ctx) if p.available()]
    if not chain:
        raise ImagesUnavailable(f"No image service is set up: {SETUP_HINT}")
    limit = ctx.settings.images.daily_limit
    if used_today(ctx) >= limit:
        raise ImagesUnavailable(f"Today's limit of {limit} AI images is reached (Settings → Images); it resets at "
                                "midnight UTC")
    prompt = guardrails.redact(prompt, ctx.blocklist)
    sleep = ctx.sleep or time.sleep
    errors: list[tuple[str, ImageError]] = []
    with client_for(ctx) as client:
        for provider in chain:
            if _out_today(ctx, provider.name):
                continue
            for attempt in range(2):
                try:
                    res = provider.generate(client, prompt, width, height)
                except ImageError as exc:
                    record(ctx, provider.name, card_id, purpose, error=exc)
                    log.info(f"images: {provider.name}: {exc.public()}")
                    if exc.retryable and attempt == 0:
                        sleep(3)
                        continue
                    errors.append((provider.name, exc))
                    break
                res.path = save(ctx, card_id or "misc", res)
                record(ctx, provider.name, card_id, purpose, result=res, path=res.path)
                log.info(f"images: {provider.name} {res.model} made a {res.width}x{res.height} image in {res.ms} ms "
                         f"({len(res.data)} bytes)")
                return res
    if not errors:
        raise ImagesUnavailable("Every image service has used up today's allowance; it resets tomorrow")
    why = "; ".join(f"{name}: {e.public()}" for name, e in errors)
    if all(e.quota or e.fatal for _, e in errors):
        raise ImagesUnavailable(f"No image service can make one today ({why})")
    raise ImageError(why, retryable=True)


def save(ctx: Ctx, card_id: str, res: ImageResult) -> str:
    """Write the image under media/ai/<card>/ and return its path relative to the data root."""
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(res.content_type, "bin")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", card_id)[:64] or "misc"
    stamp = timeutil.now().strftime("%Y%m%dT%H%M%SZ")
    rel = f"{MEDIA_DIR}/{safe}/{stamp}-{ids.short_hash(res.data.hex()[:4096])[:6]}.{ext}"
    target = ctx.data_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(res.data)
    return rel


# --- prompts ----------------------------------------------------------------------------------------------------

def styled_prompt(ctx: Ctx, idea: str, *, background: bool, accent: str) -> str:
    """The model's description of the picture, plus the house look and the no-words rule."""
    idea = re.sub(r"\s+", " ", idea or "").strip()[:700] or "an abstract composition of soft shapes"
    look = ctx.settings.images.style
    if background:
        return (f"Background image: {idea}. Quiet and low in detail, with calm empty areas where text will sit; "
                f"{look}; colours that sit well with {accent}. {NO_WORDS}")
    return f"{idea}. Style: {look}; colours that sit well with {accent}. {NO_WORDS}"


def size_for(platform: str) -> tuple[int, int]:
    """What to ask for: LinkedIn portrait 4:5, X landscape 16:9 (both multiples of 16, under 1.4 megapixels)."""
    return (1024, 1280) if platform == "linkedin" else (1280, 720)


# --- media housekeeping ---------------------------------------------------------------------------------------

_STAMP = re.compile(r"^(\d{8}T\d{6}Z)")


def _file_time(name: str) -> dt.datetime | None:
    m = _STAMP.match(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def prune_media(ctx: Ctx) -> int:
    """Delete images nothing needs: replaced by a newer visual (after a day), of cards skipped, expired or failed
    for 14 days, posted over 120 days ago, or of cards that no longer exist."""
    root = ctx.data_root / MEDIA_DIR
    if not root.is_dir():
        return 0
    now = timeutil.now()
    removed = 0
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        card = ctx.store.get("cards", folder.name)
        keep = set()
        if card:
            for v in (card.get("visual"), (card.get("working") or {}).get("visual")):
                if isinstance(v, dict) and isinstance(v.get("image"), dict):
                    keep.add(Path(v["image"].get("path") or "").name)
            changed = timeutil.parse(card.get("status_changed_at") or card.get("updated_at") or card.get("created_at"))
            age = (now - changed).days if changed else 0
            gone = (card.get("status") in ("skipped", "expired", "failed") and age >= 14) or \
                (card.get("status") == "posted" and age >= 120)
        else:
            gone = True
        for f in sorted(folder.iterdir()):
            made = _file_time(f.name)
            stale = f.name not in keep and (made is None or now - made > dt.timedelta(days=1))
            if gone or stale:
                f.unlink(missing_ok=True)
                removed += 1
        if not any(folder.iterdir()):
            folder.rmdir()
    if removed:
        log.info(f"images: pruned {removed} file(s)")
    return removed
