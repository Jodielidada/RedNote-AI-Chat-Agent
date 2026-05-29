# backend/video_processor.py

import subprocess
import os
import tempfile


class VideoProcessor:
    def __init__(self):
        self.model = None  # lazy — loaded on first video

    def _ensure_model(self):
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
        try:
            cmd = ["yt-dlp", "-o", output_path, "--no-check-certificate", video_url]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(output_path):
                return True

            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X)",
                "Referer": "https://www.xiaohongshu.com/",
            }
            response = requests.get(video_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True

        except Exception as e:
            print(f"❌ 视频下载失败: {str(e)}")
            return False

    def extract_audio(self, video_path: str, audio_path: str) -> bool:
        try:
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                audio_path, "-y",
            ]
            result = subprocess.run(cmd, capture_output=True)
            return result.returncode == 0 and os.path.exists(audio_path)
        except Exception as e:
            print(f"❌ 音频提取失败: {str(e)}")
            return False

    def transcribe(self, audio_path: str, language: str = "auto") -> str:
        """Transcribe audio. Pass language="zh" to force Chinese; "auto" lets Whisper detect."""
        self._ensure_model()
        try:
            print("🎤 正在转录音频...")
            kwargs: dict = {"beam_size": 5}
            if language and language != "auto":
                kwargs["language"] = language
            segments, _ = self.model.transcribe(audio_path, **kwargs)
            text = "".join(segment.text for segment in segments)
            print("✅ 转录完成")
            return text
        except Exception as e:
            print(f"❌ 转录失败: {str(e)}")
            return ""

    def process_video(self, video_url: str, language: str = "auto") -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            audio_path = os.path.join(tmpdir, "audio.wav")
            try:
                print(f"📥 下载视频: {video_url}")
                if not self.download_video(video_url, video_path):
                    return {"success": False, "error": "视频下载失败"}

                print("🎵 提取音频...")
                if not self.extract_audio(video_path, audio_path):
                    return {"success": False, "error": "音频提取失败"}

                transcript = self.transcribe(audio_path, language=language)
                if not transcript:
                    return {"success": False, "error": "转录失败或视频无音频"}

                return {"success": True, "transcript": transcript}

            except Exception as e:
                import traceback
                return {"success": False, "error": str(e), "trace": traceback.format_exc()}


if __name__ == "__main__":
    processor = VideoProcessor()
    result = processor.process_video("视频URL")
    print(result)
