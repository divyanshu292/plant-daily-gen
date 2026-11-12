"""Image preparation in extract.py, on generated images. The reading service is never called."""

from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

import extract
from extract import ExtractionError, load_image, model_images, stored_image

RED = (255, 0, 0)


def photo(size: tuple[int, int], orientation: int | None = None, fmt: str = "JPEG", mode: str = "RGB") -> bytes:
    """A white image with a red block in its stored top-left corner."""
    im = Image.new(mode, size, "white")
    im.paste(Image.new(mode, (size[0] // 5, size[1] // 5), "red"), (0, 0))
    buf = io.BytesIO()
    if orientation is None:
        im.save(buf, format=fmt)
    else:
        exif = Image.Exif()
        exif[0x0112] = orientation  # Orientation
        im.save(buf, format=fmt, exif=exif)
    return buf.getvalue()


def decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    assert im.format == "JPEG"
    return im


def is_red(px) -> bool:
    return px[0] > 200 and px[1] < 60 and px[2] < 60


def test_exif_rotation_is_applied():
    # A phone held upright stores a landscape frame plus "rotate 90 degrees clockwise to view".
    im = load_image(photo((800, 600), orientation=6))
    assert im.size == (600, 800)
    assert im.mode == "RGB"
    # The stored top-left corner ends up top-right once the page is upright.
    assert is_red(im.getpixel((im.width - 5, 5)))
    assert not is_red(im.getpixel((5, 5)))


def test_upright_photo_is_unchanged():
    im = load_image(photo((600, 800), orientation=1))
    assert im.size == (600, 800) and is_red(im.getpixel((5, 5)))


@pytest.mark.parametrize("mode", ["RGBA", "L", "P"])
def test_png_in_any_mode_becomes_rgb(mode):
    im = load_image(photo((300, 400), fmt="PNG", mode=mode))
    assert im.mode == "RGB" and im.size == (300, 400)


def test_not_an_image():
    with pytest.raises(ExtractionError) as err:
        load_image(b"%PDF-1.4 definitely not a photo")
    assert err.value.status == 415


def test_truncated_image():
    with pytest.raises(ExtractionError) as err:
        load_image(photo((600, 800))[:500])
    assert err.value.status == 415


def test_too_large():
    with pytest.raises(ExtractionError) as err:
        load_image(b"\0" * (extract.MAX_UPLOAD_BYTES + 1))
    assert err.value.status == 413


@pytest.mark.parametrize("size", [
    (400, 560),     # tiny
    (1119, 1599),   # the sample phone photo
    (1414, 1810),   # the sample screenshot
    (3000, 4000),   # a full-resolution phone photo
    (2000, 9000),   # an extremely tall scan
])
def test_model_images_fit_the_limits(size):
    w, h = size
    full, top, bottom = (decode(b) for b in model_images(load_image(photo(size))))
    for im in (full, top, bottom):
        assert max(im.size) <= extract.MAX_EDGE
    # The whole page is only ever shrunk, keeping its proportions.
    if max(size) <= extract.MAX_EDGE:
        assert full.size == size
    else:
        assert max(full.size) == extract.MAX_EDGE
        assert full.width / full.height == pytest.approx(w / h, rel=0.01)
    # Two overlapping crops of a little over half the page each.
    for crop in (top, bottom):
        assert crop.width / crop.height == pytest.approx(w / (h * 0.56), rel=0.02)
        # Small crops are enlarged towards MIN_TILE_EDGE, but never more than 2x.
        source_long = max(w, round(h * 0.56))
        assert max(crop.size) >= min(extract.MIN_TILE_EDGE, 2 * source_long, extract.MAX_EDGE) - 1
    # The top crop starts at the top of the page (red corner), the bottom one does not.
    assert is_red(top.getpixel((3, 3))) and not is_red(bottom.getpixel((3, 3)))


def test_model_images_follow_exif_rotation():
    full, top, _ = (decode(b) for b in model_images(load_image(photo((1599, 1119), orientation=6))))
    assert full.size == (1119, 1599)
    assert is_red(top.getpixel((top.width - 3, 3)))


@pytest.mark.parametrize("size", [(400, 560), (1119, 1599), (3000, 4000)])
def test_stored_image(size):
    im = decode(stored_image(load_image(photo(size))))
    assert max(im.size) <= extract.STORED_EDGE
    assert im.size == size if max(size) <= extract.STORED_EDGE else max(im.size) == extract.STORED_EDGE


def test_reading_without_a_key_fails_cleanly():
    """With no key configured (conftest removes them) the reader refuses before any request."""
    assert extract.is_configured() is False
    with pytest.raises(ExtractionError) as err:
        asyncio.run(extract.extract_report(load_image(photo((600, 800)))))
    assert err.value.status == 503
