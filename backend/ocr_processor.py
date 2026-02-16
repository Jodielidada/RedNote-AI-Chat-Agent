# backend/ocr_processor.py

from paddleocr import PaddleOCR
import requests
from PIL import Image
from io import BytesIO


class OCRProcessor:
    def __init__(self):
        print("🔄 初始化OCR...")
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
        )
        print("✅ OCR初始化完成")

    def download_image(self, url: str) -> Image.Image:
        """下载图片"""
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.xiaohongshu.com/",
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def extract_text(self, image_url: str) -> str:
        """从图片提取文字"""
        try:
            print(f"📷 处理图片OCR: {image_url[:50]}...")

            # 下载图片
            img = self.download_image(image_url)

            # 转换为RGB（PaddleOCR需要）
            if img.mode != "RGB":
                img = img.convert("RGB")

            # 保存临时文件
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                img.save(tmp.name)
                tmp_path = tmp.name

            # OCR识别（新版 PaddleOCR 可能无 cls 参数）
            try:
                result = self.ocr.ocr(tmp_path, cls=True)
            except TypeError:
                result = self.ocr.ocr(tmp_path)

            # 提取文字
            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line[1][0]:  # 文字内容
                        texts.append(line[1][0])

            # 删除临时文件
            import os

            os.unlink(tmp_path)

            extracted = " ".join(texts)
            print(f"✅ OCR完成，提取{len(texts)}行文字")
            return extracted

        except Exception as e:
            print(f"❌ OCR失败: {str(e)}")
            return ""

    def process_images(self, image_urls: list) -> str:
        """批量处理多张图片"""
        all_texts = []

        for i, url in enumerate(image_urls, 1):
            print(f"📷 处理第 {i}/{len(image_urls)} 张图片")
            text = self.extract_text(url)
            if text:
                all_texts.append(f"[图片{i}文字]\n{text}")

        return "\n\n".join(all_texts)


# 测试代码
if __name__ == "__main__":
    processor = OCRProcessor()
    text = processor.extract_text("图片URL")
    print(text)
