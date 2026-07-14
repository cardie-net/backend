import io

from PIL import Image


def optimize_image(image_bytes: bytes, max_size: tuple[int, int] = (512, 512)) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as img:
        # Convert to RGB if it has an alpha channel or is paletted
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.thumbnail(max_size)

        output = io.BytesIO()
        img.save(output, format="WEBP", quality=80)
        return output.getvalue()
