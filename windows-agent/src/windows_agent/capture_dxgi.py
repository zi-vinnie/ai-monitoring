"""DXGI Desktop Duplication capture. Windows-only (dxcam).

GDI/mss screen capture returns an all-black frame for exclusive-fullscreen
DirectX/OpenGL games (Rocket League and many others) because those games bypass
the desktop compositor and present straight to the GPU. The Desktop Duplication
API reads the GPU output and captures them correctly.

This is used only as a fallback in `capture.py` when the mss frame comes back
black, so it never touches normal desktop captures. Every failure path here
returns None; the caller then keeps the (black) mss frame, matching prior
behaviour. dxcam is import-guarded so the project still resolves off-Windows.
"""

from __future__ import annotations

import mss.tools

try:
    import dxcam
except ImportError:  # pragma: no cover - dxcam is only installable on Windows
    dxcam = None

# A single GPU won't realistically drive more than a handful of outputs; this
# just bounds the enumeration loop so a misbehaving create() can't spin forever.
_MAX_OUTPUTS = 15


def dxgi_available() -> bool:
    return dxcam is not None


def _output_idx_for_hmonitor(hmonitor: int) -> int | None:
    """Find the dxcam output index whose monitor matches the given HMONITOR.

    dxcam exposes no public monitor->output map, so we match on each output's
    HMONITOR (carried on the internal Output object). Anything unexpected
    (attribute gone, create() raising past the last output) returns None and the
    caller falls back to the mss frame.
    """
    for idx in range(_MAX_OUTPUTS):
        try:
            camera = dxcam.create(output_idx=idx, output_color="BGRA")
        except Exception:
            return None
        if camera is None:
            return None
        try:
            if int(camera._output.hmonitor) == hmonitor:
                return idx
        except AttributeError:
            return None
    return None


def capture_monitor_png(hmonitor: int | None) -> bytes | None:
    """Capture the monitor identified by `hmonitor` via Desktop Duplication.

    Returns PNG bytes, or None if dxcam is unavailable, the monitor can't be
    matched, or no frame is produced.
    """
    if dxcam is None:
        return None
    try:
        # No focused window -> no known monitor; fall back to the primary output.
        output_idx = _output_idx_for_hmonitor(hmonitor) if hmonitor is not None else 0
        if output_idx is None:
            return None
        camera = dxcam.create(output_idx=output_idx, output_color="BGRA")
        if camera is None:
            return None
        # new_frame_only=False returns the latest frame even if the screen hasn't
        # changed since the last grab (dxcam otherwise returns None in that case).
        frame = camera.grab(new_frame_only=False)
        if frame is None:
            return None
        height, width = frame.shape[0], frame.shape[1]
        # BGRA (channels B,G,R,A at indices 0..3) -> RGB via a numpy slice; no
        # OpenCV needed, which BGRA output is specifically chosen to avoid.
        rgb = frame[:, :, 2::-1]
        return mss.tools.to_png(rgb.tobytes(), (width, height))
    except Exception:
        return None
