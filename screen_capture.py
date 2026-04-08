import base64
import io
import time
from config_manager import config

try:
    import dxcam
except ImportError:
    dxcam = None

from mss import mss
from PIL import Image, ImageDraw
import win32api


class ScreenCapturer:
    def __init__(self):
        self.use_dxcam = False
        self.dxcamera = None
        self.sct = None

        if dxcam is not None:
            try:
                self.dxcamera = dxcam.create(output_color="RGB")
                if self.dxcamera:
                    # Prime the frame buffer so the first real grab() isn't None
                    self.dxcamera.grab()
                    self.use_dxcam = True
                else:
                    raise RuntimeError("DXCam returned None")
            except Exception as e:
                print(f"DXCam init failed, falling back to mss: {e}")

        if not self.use_dxcam:
            self.sct = mss()

    def get_cursor_pos(self):
        """Returns (x, y) cursor position."""
        return win32api.GetCursorPos()

    def capture_base64(self) -> str:
        """Captures the screen, draws cursor overlay, returns base64 JPEG."""
        start = time.perf_counter()
        img = None

        # 1. Capture screen
        if self.use_dxcam:
            frame = self.dxcamera.grab()
            if frame is not None:
                img = Image.fromarray(frame)

        if img is None:
            # mss fallback
            if self.sct is None:
                self.sct = mss()
            monitor = self.sct.monitors[1]
            sct_img = self.sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # 2. Remember original width, then downscale for LLM efficiency
        original_width = img.width
        max_width = int(config.get("capture_max_width", 1280))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # 3. Draw cursor directly on RGB image (no alpha compositing needed)
        cx, cy = self.get_cursor_pos()
        scale = img.width / original_width if original_width else 1.0
        cx = int(cx * scale)
        cy = int(cy * scale)

        draw = ImageDraw.Draw(img)
        cursor_poly = [
            (cx, cy),
            (cx, cy + 17),
            (cx + 4, cy + 13),
            (cx + 8, cy + 20),
            (cx + 10, cy + 19),
            (cx + 7, cy + 12),
            (cx + 12, cy + 12),
        ]
        draw.polygon(cursor_poly, fill=(0, 0, 0), outline=(255, 255, 255))

        # 4. Compress to JPEG and base64 encode
        quality = int(config.get("capture_jpeg_quality", 80))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        elapsed = (time.perf_counter() - start) * 1000
        print(f"DEBUG: Screen capture took {elapsed:.1f}ms ({img.width}x{img.height}, {len(b64)//1024}KB)")
        return b64


if __name__ == "__main__":
    capturer = ScreenCapturer()
    b64 = capturer.capture_base64()
    print(f"Captured size {len(b64)} characters")
