import io

from PIL import Image

from ..config import settings


def optimize_image(
    image_bytes: bytes, max_size: tuple[int, int] | None = None
) -> bytes:
    """Optimize an image by resizing and converting to WEBP."""
    if not image_bytes:
        raise ValueError("Empty image bytes")

    if max_size is None:
        max_size = (settings.AVATAR_MAX_SIZE, settings.AVATAR_MAX_SIZE)

    with Image.open(io.BytesIO(image_bytes)) as img:
        # Convert paletted images to RGBA to preserve transparency
        if img.mode == "P":
            img = img.convert("RGBA")

        img.thumbnail(max_size)

        output = io.BytesIO()
        img.save(output, format="WEBP", quality=settings.IMAGE_QUALITY)
        return output.getvalue()


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
