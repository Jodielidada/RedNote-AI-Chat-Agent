# backend/video_processor.py

import subprocess
import os
import tempfile


class VideoProcessor:
    def __init__(self):
        self.model = None  # 懒加载，用到视频时再加载

    def _ensure_model(self):
        """首次处理视频时再加载 faster-whisper"""
        if self.model is None:
            try:
                from faster_whisper import WhisperModel
                print("🔄 加载 faster-whisper 模型...")
                self.model = WhisperModel("base", device="cpu", compute_type="int8")
                print("✅ 模型加载完成")
            except ImportError:
                raise RuntimeError(
                    "处理视频需要安装 faster-whisper，请运行: pip install faster-whisper"
                )

    def download_video(self, video_url: str, output_path: str) -> bool:
        """下载视频"""
        try:
            # 方法1: 使用yt-dlp
            cmd = [
                "yt-dlp",
                "-o",
                output_path,
                "--no-check-certificate",
                video_url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and os.path.exists(output_path):
                return True

            # 方法2: 直接下载（如果yt-dlp失败）
            import requests

            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)",
                "Referer": "https://www.xiaohongshu.com/",
            }
            response = requests.get(
                video_url, headers=headers, stream=True, timeout=60
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return True

        except Exception as e:
            print(f"❌ 视频下载失败: {str(e)}")
            return False

    def extract_audio(self, video_path: str, audio_path: str) -> bool:
        """从视频提取音频"""
        try:
            cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-vn",  # 不要视频
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",  # Whisper推荐采样率
                "-ac",
                "1",  # 单声道
                audio_path,
                "-y",  # 覆盖已存在文件
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
            )

            return result.returncode == 0 and os.path.exists(audio_path)

        except Exception as e:
            print(f"❌ 音频提取失败: {str(e)}")
            return False

    def transcribe(self, audio_path: str) -> str:
        """音频转文字"""
        self._ensure_model()
        try:
            print("🎤 正在转录音频...")
            segments, _ = self.model.transcribe(
                audio_path,
                language="zh",  # 中文
                beam_size=5,
            )
            text = "".join(segment.text for segment in segments)
            print("✅ 转录完成")
            return text
        except Exception as e:
            print(f"❌ 转录失败: {str(e)}")
            return ""

    def process_video(self, video_url: str) -> dict:
        """
        处理视频主流程
        返回转录文字
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            audio_path = os.path.join(tmpdir, "audio.wav")

            try:
                # 1. 下载视频
                print(f"📥 下载视频: {video_url}")
                if not self.download_video(video_url, video_path):
                    return {
                        "success": False,
                        "error": "视频下载失败",
                    }

                # 2. 提取音频
                print("🎵 提取音频...")
                if not self.extract_audio(video_path, audio_path):
                    return {
                        "success": False,
                        "error": "音频提取失败",
                    }

                # 3. 转录文字
                transcript = self.transcribe(audio_path)

                if not transcript:
                    return {
                        "success": False,
                        "error": "转录失败或视频无音频",
                    }

                return {
                    "success": True,
                    "transcript": transcript,
                }

            except Exception as e:
                import traceback

                return {
                    "success": False,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                }


# 测试代码
if __name__ == "__main__":
    processor = VideoProcessor()
    result = processor.process_video("视频URL")
    print(result)
