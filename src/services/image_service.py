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
        max_size = (settings.IMAGE_MAX_SIZE, settings.IMAGE_MAX_SIZE)

    with Image.open(io.BytesIO(image_bytes)) as img:
        # Convert paletted images to RGBA to preserve transparency
        if img.mode == "P":
            img = img.convert("RGBA")

        img.thumbnail(max_size)

        output = io.BytesIO()
        img.save(output, format="WEBP", quality=settings.IMAGE_QUALITY)
        return output.getvalue()
