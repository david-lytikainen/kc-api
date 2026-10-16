from io import BytesIO
from pathlib import Path

from PIL import Image


def prepare_image_upload(content: bytes, filename: str, content_type: str | None) -> tuple[bytes, str, str | None]:
    """Convert supported images to AVIF, preserving the original if conversion fails."""
    try:
        from pillow_avif import AvifImagePlugin  # noqa: F401

        with Image.open(BytesIO(content)) as image:
            image.load()
            if image.mode not in ("RGB", "RGBA", "L", "LA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            output = BytesIO()
            image.save(output, format="AVIF", quality=50, speed=6)
        return output.getvalue(), f"{Path(filename).stem or 'image'}.avif", "image/avif"
    except Exception:
        return content, filename, content_type
