# backend/ocr_processor.py

import os
import tempfile
import requests
from PIL import Image
from io import BytesIO


class OCRProcessor:
    def __init__(self):
        self._ocr = None  # lazy — loaded on first use

    def _ensure_ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR
            print("🔄 初始化OCR...")
            self._ocr = PaddleOCR(use_angle_cls=True, lang="ch")
            print("✅ OCR初始化完成")

    def download_image(self, url: str) -> Image.Image:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.xiaohongshu.com/",
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def extract_text(self, image_url: str) -> str:
        try:
            print(f"📷 处理图片OCR: {image_url[:50]}...")
            self._ensure_ocr()

            img = self.download_image(image_url)
            if img.mode != "RGB":
                img = img.convert("RGB")

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path = tmp.name
                    img.save(tmp_path)

                try:
                    result = self._ocr.ocr(tmp_path, cls=True)
                except TypeError:
                    result = self._ocr.ocr(tmp_path)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line[1][0]:
                        texts.append(line[1][0])

            extracted = " ".join(texts)
            print(f"✅ OCR完成，提取{len(texts)}行文字")
            return extracted

        except Exception as e:
            print(f"❌ OCR失败: {str(e)}")
            return ""

    def process_images(self, image_urls: list) -> str:
        all_texts = []
        for i, url in enumerate(image_urls, 1):
            print(f"📷 处理第 {i}/{len(image_urls)} 张图片")
            text = self.extract_text(url)
            if text:
                all_texts.append(f"[图片{i}文字]\n{text}")
        return "\n\n".join(all_texts)


if __name__ == "__main__":
    processor = OCRProcessor()
    text = processor.extract_text("图片URL")
    print(text)
