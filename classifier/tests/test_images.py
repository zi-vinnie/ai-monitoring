import base64
import io

from PIL import Image

from classifier.images import encode_image


def _write_png(path, size):
    Image.new("RGB", size, (123, 50, 200)).save(path, format="PNG")


def _decode(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def test_downscales_large_image_preserving_aspect(tmp_path):
    path = tmp_path / "big.png"
    _write_png(path, (3200, 2000))
    out = _decode(encode_image(path, max_edge=1280))
    assert max(out.size) == 1280
    assert out.size == (1280, 800)  # 16:10 aspect preserved


def test_leaves_smaller_image_untouched(tmp_path):
    path = tmp_path / "small.png"
    _write_png(path, (800, 600))
    out = _decode(encode_image(path, max_edge=1280))
    assert out.size == (800, 600)


def test_zero_max_edge_disables_resize(tmp_path):
    path = tmp_path / "big.png"
    _write_png(path, (3200, 2000))
    out = _decode(encode_image(path, max_edge=0))
    assert out.size == (3200, 2000)
