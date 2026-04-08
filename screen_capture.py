import base64
import io
import time
import dxcam
from mss import mss
from PIL import Image, ImageDraw
import win32api
from config_manager import config

class ScreenCapturer:
    def __init__(self):
        self.use_dxcam = True
        try:
            self.dxcamera = dxcam.create(output_color="RGB")
            if not self.dxcamera:
                 raise RuntimeError("DXCam returned None")
        except Exception as e:
            print(f"DXCam initialization failed, falling back to mss: {e}")
            self.use_dxcam = False
            self.sct = mss()

    def get_cursor_pos(self):
        """Returns (x, y) cursor position."""
        return win32api.GetCursorPos()

    def capture_base64(self) -> str:
        """Captures the screen, draws cursor, returns base64 JPEG."""
        start = time.perf_counter()
        img = None
        
        # 1. Capture screen
        if self.use_dxcam:
            frame = self.dxcamera.grab()
            if frame is not None:
                img = Image.fromarray(frame)
            else:
                # dxcam failed to grab, fallback
                if not hasattr(self, 'sct'):
                    self.sct = mss()
        
        if img is None:
            # mss fallback
            monitor = self.sct.monitors[1]  # primary monitor
            sct_img = self.sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # 2. Draw custom cursor at cursor position
        cx, cy = self.get_cursor_pos()
        
        # Overlay for alpha drawing
        overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Read color from config, default to blue (like the image provided)
        color_str = config.get("cursor_color", "66,133,244")
        try:
            r_c, g_c, b_c = map(int, color_str.split(","))
        except Exception:
            r_c, g_c, b_c = 66, 133, 244
            
        # Draw mouse cursor shape (black arrow with white outline at actual position)
        cursor_poly = [
            (cx, cy),
            (cx, cy + 17),
            (cx + 4, cy + 13),
            (cx + 8, cy + 20),
            (cx + 10, cy + 19),
            (cx + 7, cy + 12),
            (cx + 12, cy + 12)
        ]
        draw.polygon(cursor_poly, fill=(0, 0, 0, 255), outline=(255, 255, 255, 255))
        
        # We don't draw the blue triangle here anymore, because the actual buddy_window.py Widget 
        # is a blue triangle that sits next to the cursor and is natively captured by DXcam!
        
        # Composite
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay).convert("RGB")
        
        # 3. Compress to JPEG and base64 encode
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        elapsed = (time.perf_counter() - start) * 1000
        print(f"DEBUG: Screen capture took {elapsed:.1f}ms")
        return b64

if __name__ == "__main__":
    # Test script
    capturer = ScreenCapturer()
    b64 = capturer.capture_base64()
    print(f"Captured size {len(b64)} characters")
