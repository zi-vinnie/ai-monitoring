import base64
import io
from pathlib import Path

from PIL import Image


def encode_image(path: Path, max_edge: int = 1280) -> str:
    """Load a screenshot, optionally downscale it, and return base64 PNG bytes.

    Vision models tile an image into a fixed budget of tokens, so a full-size
    screenshot (these can be 3200x2000) can blow past a small model's context
    window (e.g. qwen2.5vl at 4096) and get rejected. Shrinking the longest edge
    to ``max_edge`` keeps the request within context and speeds up inference,
    with negligible accuracy loss for coarse activity labels — the model can
    still read window chrome and large text.

    Only ever downscales (never upscales) and preserves aspect ratio. Pass
    ``max_edge <= 0`` to send the image at full resolution.
    """
    with Image.open(path) as im:
        im = im.convert("RGB")
        if max_edge > 0 and max(im.size) > max_edge:
            im.thumbnail((max_edge, max_edge))
        buffer = io.BytesIO()
        im.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
