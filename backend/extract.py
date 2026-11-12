"""Image -> DailySystemReport, using Gemini vision with a JSON response schema."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from dataclasses import dataclass

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from report_schema import DailySystemReport

# Models to try, in order. Both read every cell of the two sample pages
# correctly when benchmarked against hand-checked transcriptions; the second is
# used when the first is overloaded, over quota or too slow.
MODELS = [m.strip() for m in os.getenv("EXTRACTION_MODEL", "gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",")
          if m.strip()]
MODEL = MODELS[0]
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# A page normally takes 10 to 40 seconds.
REQUEST_TIMEOUT_S = 75.0
# Tries per model for failures that usually clear on their own (overloaded
# model, truncated or malformed JSON).
TRANSIENT_ATTEMPTS = 2

# Anything larger than this is downscaled by the model anyway, so sending more
# only costs upload bytes.
MAX_EDGE = 2576
# Half-page tiles below this size are enlarged so small print stays legible.
MIN_TILE_EDGE = 1800
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
STORED_EDGE = 1800

SYSTEM_PROMPT = """\
You transcribe the "Daily System Report" of Tenughat Vidyut Nigam Limited (TVNL), \
a thermal power station with two 210 MW units. The form is a single typed page: a \
header with the report date, a daily table (S.No 1-15), a "Monthly Progressive \
System Report" table (16-26), "Status of Fuel" (27-32), "Electrical System" load \
flow (33), "Energy Flow" (34-37) and two remarks lines (38, 39).

The numbers you transcribe are loaded straight into the plant's generation \
database, where they feed monthly and yearly totals, so a single wrong digit \
matters. Work as a careful transcriber, not an analyst:

- Copy each cell exactly as printed, keeping every digit and decimal place, \
including trailing zeros ("2656.00", "0.000", "0:00:00").
- Do not calculate, round, correct or infer anything. If two cells look \
inconsistent with each other, still write what is printed in each.
- A cell that is blank, or lies outside the photographed area, is an empty \
string. A cell printed as dashes is "----".
- Handwriting, pen marks, brackets drawn in the margin, signatures and stamps \
are not data. Ignore them unless they hide a printed value, in which case list \
that cell in unclear_cells and give your best reading.
- Read each value from the row its S.No belongs to and the column it sits \
under. The rows are closely spaced, so check the row number at the left edge \
before reading across.

You receive the same page several times: first the whole page for layout, then \
enlarged crops of the upper and lower parts (they overlap in the middle). Use \
the enlarged crops to read the digits and the whole page to confirm which row \
and column each value belongs to.\
"""

USER_PROMPT = (
    "Transcribe every cell of this Daily System Report into the schema. "
    "Image 1 is the full page; the following images are enlarged crops of the same page."
)


class ExtractionError(Exception):
    """Extraction could not be completed. `status` is the HTTP status to return."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class Extraction:
    report: DailySystemReport
    model: str
    usage: dict


def _fit(im: Image.Image, max_edge: int, min_edge: int = 0) -> Image.Image:
    long_edge = max(im.size)
    if long_edge > max_edge:
        scale = max_edge / long_edge
    elif min_edge and long_edge < min_edge:
        scale = min(min_edge / long_edge, 2.0)
    else:
        return im
    return im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)


def _jpeg(im: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def load_image(raw: bytes) -> Image.Image:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ExtractionError("Image is larger than 15 MB.", status=413)
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ExtractionError("That file is not a readable image (use JPG or PNG).", status=415) from exc
    # Phone photos carry their rotation in EXIF; apply it so the page is upright.
    return ImageOps.exif_transpose(im).convert("RGB")


def model_images(im: Image.Image) -> list[bytes]:
    """Full page plus two overlapping half-page crops, as JPEG bytes."""
    w, h = im.size
    top = im.crop((0, 0, w, round(h * 0.56)))
    bottom = im.crop((0, round(h * 0.44), w, h))
    return [
        _jpeg(_fit(im, MAX_EDGE), 90),
        _jpeg(_fit(top, MAX_EDGE, MIN_TILE_EDGE), 92),
        _jpeg(_fit(bottom, MAX_EDGE, MIN_TILE_EDGE), 92),
    ]


def stored_image(im: Image.Image) -> bytes:
    """Compact copy kept with the report record for later review."""
    return _jpeg(_fit(im, STORED_EDGE), 82)


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def is_configured() -> bool:
    return bool(_api_key())


def _response_schema() -> dict:
    """The page model as the schema dialect Gemini accepts: no $ref, upper-case
    types, and an explicit property order so cells come back in page order."""
    source = DailySystemReport.model_json_schema()
    defs = source.get("$defs", {})

    def convert(node: dict) -> dict:
        if "$ref" in node:
            resolved = convert(defs[node["$ref"].rsplit("/", 1)[-1]])
            if node.get("description"):
                resolved["description"] = node["description"]
            return resolved
        out: dict = {"type": node["type"].upper()}
        if node.get("description"):
            out["description"] = node["description"]
        if node["type"] == "object":
            out["properties"] = {k: convert(v) for k, v in node["properties"].items()}
            out["required"] = list(node["properties"])
            out["propertyOrdering"] = list(node["properties"])
        elif node["type"] == "array":
            out["items"] = convert(node["items"])
        return out

    return convert(source)


_SCHEMA = _response_schema()
_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)
    return _http


class _Transient(Exception):
    """A failure worth one more attempt on the same model."""


class _NextModel(Exception):
    """A failure of this model in particular: move on to the next one."""


async def _generate(model: str, body: dict) -> dict:
    """One call to generateContent, with errors mapped to what the uploader should see."""
    try:
        resp = await _client().post(
            f"{API_BASE}/models/{model}:generateContent",
            headers={"x-goog-api-key": _api_key() or ""},
            json=body,
        )
    except httpx.TimeoutException as exc:
        raise _NextModel(f"The reading service took longer than {REQUEST_TIMEOUT_S:.0f} seconds.") from exc
    except httpx.HTTPError as exc:
        raise _Transient("Could not reach the reading service. Check the server's network.") from exc

    if resp.status_code == 200:
        return resp.json()
    try:
        message = resp.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = resp.text[:300]
    if resp.status_code in (401, 403) or "API key" in message:
        raise ExtractionError(f"The server's GEMINI_API_KEY was rejected: {message}", status=503)
    if resp.status_code == 429:
        raise _NextModel(f"The reading model '{model}' is over its quota or rate limit.")
    if resp.status_code == 404:
        raise _NextModel(f"The reading model '{model}' is not available to this API key.")
    if resp.status_code >= 500:
        raise _Transient(f"The reading service failed ({resp.status_code}): {message}")
    raise ExtractionError(f"The reading service rejected the request: {message}", status=502)


async def extract_report(im: Image.Image, recheck: list[str] | None = None, model: str | None = None) -> Extraction:
    """Transcribe the report. `recheck` lists failed consistency checks from a
    previous attempt so the model looks at those cells again."""
    if not is_configured():
        raise ExtractionError(
            "GEMINI_API_KEY is not set on the server, so report images cannot be read. "
            "Add it to the .env file (or the hosting environment) and restart.",
            status=503,
        )
    parts: list[dict] = [
        {"inlineData": {"mimeType": "image/jpeg", "data": base64.standard_b64encode(data).decode("ascii")}}
        for data in model_images(im)
    ]
    text = USER_PROMPT
    if recheck:
        text += (
            "\n\nA first transcription of this page did not add up. The arithmetic printed on the form "
            "is normally self-consistent, so one of the cells below was probably misread. Look at each "
            "of them again in the enlarged crops, digit by digit, and transcribe the whole page afresh. "
            "If the page really does print these values, keep them as printed.\n- "
            + "\n- ".join(recheck)
        )
    parts.append({"text": text})
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA,
            "maxOutputTokens": 32768,
        },
    }

    last = "The reading service failed."
    for name in ([model] if model else MODELS):
        for attempt in range(TRANSIENT_ATTEMPTS):
            if attempt:
                await asyncio.sleep(2)
            try:
                return _parse(await _generate(name, body), name)
            except _Transient as exc:
                last = str(exc)
            except _NextModel as exc:
                last = str(exc)
                break
    raise ExtractionError(f"{last} Try again in a minute.", status=502)


def _parse(data: dict, model: str) -> Extraction:
    """Turn a generateContent response into a report, or say why it cannot be used."""
    blocked = (data.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise ExtractionError(f"The reading service declined to process this image ({blocked}).", status=422)
    candidate = (data.get("candidates") or [{}])[0]
    finish = candidate.get("finishReason")
    answer = "".join(p.get("text", "") for p in (candidate.get("content") or {}).get("parts", [])
                     if not p.get("thought"))
    if finish == "SAFETY":
        raise ExtractionError("The reading service declined to process this image.", status=422)
    if finish != "STOP" or not answer:
        raise _Transient(f"The reading service returned an incomplete transcription ({finish}).")
    try:
        report = DailySystemReport.model_validate_json(answer)
    except ValidationError as exc:
        raise _Transient("The reading service returned a malformed transcription.") from exc
    usage = data.get("usageMetadata") or {}
    return Extraction(
        report=report,
        model=data.get("modelVersion") or model,
        usage={
            "inputTokens": usage.get("promptTokenCount"),
            "outputTokens": usage.get("candidatesTokenCount"),
            "thinkingTokens": usage.get("thoughtsTokenCount"),
        },
    )
