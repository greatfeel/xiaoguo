"""TTS Generator Module
集中管理 TTS 合成与磁盘缓存，供 main.py 管道和 webapp.py /api/tts 共用。
"""
import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import edge_tts
except ImportError:
    edge_tts = None


class TTSGenerator:
    """TTS 音频生成器，支持预生成和磁盘缓存。"""

    def __init__(self, config: Dict[str, Any], cache_dir: str = "tts_cache"):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    # ── 内部工具 ──────────────────────────────────────────

    def _resolve_profile(self, lang: str, style: str) -> tuple:
        """根据语言和风格选择 voice/rate。"""
        style = (style or "standard").lower()
        if style not in ["standard", "gentle", "broadcast"]:
            style = "standard"

        if lang == "en":
            defaults = {
                "standard": ("en-US-EmmaMultilingualNeural", "-15%"),
                "gentle":   ("en-US-JennyNeural", "-25%"),
                "broadcast":("en-US-GuyNeural", "-10%"),
            }
        else:
            defaults = {
                "standard": ("zh-CN-XiaoxiaoNeural", "-8%"),
                "gentle":   ("zh-CN-XiaoyiNeural", "-18%"),
                "broadcast":("zh-CN-YunyangNeural", "-5%"),
            }

        voice, rate = defaults[style]
        lang_key = "EN" if lang == "en" else "ZH"
        voice = self.config.get(f"EDGE_TTS_VOICE_{lang_key}_{style.upper()}", voice)
        rate  = self.config.get(f"EDGE_TTS_RATE_{lang_key}_{style.upper()}", rate)
        return voice, rate

    async def _synthesize(self, text: str, lang: str, style: str) -> bytes:
        """调用 Edge TTS 生成音频字节流。"""
        voice, rate = self._resolve_profile(lang, style)
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
        chunks = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk.get("data", b""))
        return b"".join(chunks)

    # ── 公开接口 ──────────────────────────────────────────

    @staticmethod
    def normalize_text(text: str) -> str:
        """清理 TTS 文本（去除 HTML 标签、URL、多余空白）。"""
        if not text:
            return ""
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = re.sub(r"https?://\S+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def cache_path(self, text: str, lang: str, style: str) -> Path:
        """计算缓存文件路径（按内容 hash 命名，与文章无关）。"""
        h = hashlib.sha256(f"{lang}::{style}::{text}".encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.mp3"

    def synthesize_with_cache(
        self, text: str, lang: str, style: str = "standard"
    ) -> Optional[bytes]:
        """生成音频，命中磁盘缓存则直接返回，否则合成后写入缓存。
        返回 None 表示生成失败或 edge-tts 不可用。
        """
        if edge_tts is None:
            logger.warning("edge-tts 未安装，无法生成音频")
            return None

        text = self.normalize_text(text)
        if not text:
            return None
        text = text[:2500]  # 防止超长请求导致超时

        cached = self.cache_path(text, lang, style)
        if cached.exists():
            logger.debug("TTS 命中磁盘缓存: %s", cached.name)
            return cached.read_bytes()

        try:
            audio_bytes = asyncio.run(self._synthesize(text, lang, style))
        except Exception as exc:
            logger.warning("Edge TTS 合成失败: %s", exc)
            return None

        if audio_bytes:
            cached.write_bytes(audio_bytes)
            logger.info("TTS 已缓存: %s", cached.name)

        return audio_bytes

    def generate_article_audio(
        self,
        title: str,
        content: str,
        lang: str,
        output_path: Path,
        style: str = "standard",
    ) -> bool:
        """为文章预生成 MP3 文件并保存到 output_path。
        文件已存在则跳过（幂等）。返回是否成功。

        注意：内部调用 synthesize_with_cache，音频字节同时存入两处：
          1. tts_cache/{hash}.mp3 —— 供 /api/tts 端点复用（风格切换等场景）
          2. output_path（如 news/.../stem_zh.mp3）—— 供页面直接访问
        这是有意为之：两者服务不同用途，tts_cache 条目不会因文章归档而失效。
        """
        if edge_tts is None:
            return False
        if output_path.exists():
            logger.debug("音频已存在，跳过: %s", output_path.name)
            return True

        sep = ". " if lang == "en" else "。"
        full_text = self.normalize_text(title + sep + content)
        if not full_text:
            return False

        audio_bytes = self.synthesize_with_cache(full_text, lang, style)
        if not audio_bytes:
            return False

        output_path.write_bytes(audio_bytes)
        logger.info("已预生成音频: %s", output_path.name)
        return True
