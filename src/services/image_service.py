import io

from PIL import Image, UnidentifiedImageError

from ..config import settings

# Pillow format names we accept. Every accepted image is re-encoded to WEBP, so
# exotic/undecodable formats are rejected instead of being stored.
ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF", "BMP"})
# Modes WEBP can encode directly; anything else is converted to RGBA first.
_WEBP_MODES = frozenset({"RGB", "RGBA", "L"})


class UnsupportedImageError(ValueError):
    """Raised when an upload is not a decodable image in an allowed format."""


class ImageTooLargeError(ValueError):
    """Raised when an image exceeds MAX_IMAGE_PIXELS."""


def optimize_image(
    image_bytes: bytes, max_size: tuple[int, int] | None = None
) -> bytes:
    """Validate an uploaded image, strip its metadata and convert it to WEBP."""
    if not image_bytes:
        raise UnsupportedImageError("Empty upload")

    if max_size is None:
        max_size = (settings.AVATAR_MAX_SIZE, settings.AVATAR_MAX_SIZE)

    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            if opened.format not in ALLOWED_IMAGE_FORMATS:
                raise UnsupportedImageError(
                    f"Unsupported image format: {opened.format}"
                )
            # Checked before any pixel data is decoded, so a small upload cannot
            # force a huge decode (decompression bomb).
            if opened.width * opened.height > settings.MAX_IMAGE_PIXELS:
                raise ImageTooLargeError("Image dimensions too large")

            img = opened if opened.mode in _WEBP_MODES else opened.convert("RGBA")
            img.thumbnail(max_size)

            # Copy pixels into a fresh image so EXIF/XMP/ICC/comments and any
            # embedded EXIF thumbnail from the upload are dropped.
            clean = Image.new(img.mode, img.size)
            clean.paste(img)

            output = io.BytesIO()
            clean.save(output, format="WEBP", quality=settings.IMAGE_QUALITY)
            return output.getvalue()
    except (UnsupportedImageError, ImageTooLargeError):
        raise
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError("Image dimensions too large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UnsupportedImageError("Unsupported or corrupt image") from exc


def collect_image_urls(*sides: list | None) -> list[str]:
    """Collect all image element URLs from one or more card sides (front/back)."""
    urls: list[str] = []
    for elements in sides:
        for element in elements or []:
            if isinstance(element, dict):
                is_image = element.get("type") == "image"
                url = element.get("url") if is_image else None
            else:
                is_image = getattr(element, "type", None) == "image"
                url = getattr(element, "url", None) if is_image else None
            if url:
                urls.append(url)
    return urls
