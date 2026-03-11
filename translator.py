"""
Translation Module
使用大模型 API 翻译新闻内容
"""
import os
import re
import logging
import anthropic
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class Translator:
    """新闻翻译器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._setup_client()

    def _setup_client(self):
        """设置 Anthropic 客户端"""
        # 从配置或环境变量获取 API 密钥
        auth_token = self.config.get('ANTHROPIC_AUTH_TOKEN', '')

        # 支持环境变量格式 ${VAR_NAME}
        if auth_token.startswith('${') and auth_token.endswith('}'):
            env_var = auth_token[2:-1]
            auth_token = os.environ.get(env_var, '')

        # 如果环境变量中也没有，尝试直接使用
        if not auth_token:
            auth_token = os.environ.get('ANTHROPIC_API_KEY', '')

        base_url = self.config.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
        model = self.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

        self.client = anthropic.Anthropic(
            api_key=auth_token,
            base_url=base_url
        )
        self.model = model
        logger.info(f"Translator initialized with model: {model}")

    def translate_news(self, news_item: Dict[str, Any]) -> Dict[str, Any]:
        """翻译单条新闻（英文->中文），保留英文原文"""
        try:
            title = news_item.get('title', '')
            description = news_item.get('description', '')
            content = news_item.get('content', '')

            translated_title = self._translate(title) if title else ''
            translated_description = self._translate(description) if description else ''
            translated_content = self._translate_html(content) if content else ''

            return {
                **news_item,
                'title': translated_title or title,
                'description': translated_description or description,
                'content': translated_content or content,
                'title_en': title,        # 英文原标题
                'content_en': content,    # 英文原内容
            }

        except Exception as e:
            logger.error(f"Error translating news: {e}")
            return news_item

    def _get_text_from_response(self, message) -> str:
        """从 API 响应中提取文本，处理不同类型的块"""
        text_parts = []
        for block in message.content:
            # 检查块类型，获取文本内容
            if hasattr(block, 'text'):
                text_parts.append(block.text)
            elif isinstance(block, dict):
                # 处理字典形式的响应
                text_parts.append(block.get('text', ''))
        return ''.join(text_parts)

    def _translate(self, text: str) -> str:
        """翻译纯文本"""
        if not text or not text.strip():
            return text

        try:
            prompt = f"""请将以下英文翻译为中文，保持原文的语气和专业术语：

{text}"""

            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return self._get_text_from_response(message).strip()

        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text

    def _translate_html(self, html_content: str) -> str:
        """翻译 HTML 内容，保留 HTML 标签"""
        if not html_content:
            return html_content

        # 检查是否包含 HTML 标签
        if not re.search(r'<[^>]+>', html_content):
            # 纯文本，直接翻译
            return self._translate(html_content)

        try:
            prompt = f"""请将以下 HTML 内容翻译为中文。请：
1. 翻译所有可见文本为中文
2. 保留所有 HTML 标签和结构不变
3. 保持原文的格式和布局

HTML 内容：
{html_content}"""

            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return self._get_text_from_response(message).strip()

        except Exception as e:
            logger.error(f"HTML translation error: {e}")
            # 尝试提取纯文本翻译
            return self._translate(html_content)

    def translate_batch(self, news_items: list) -> list:
        """批量翻译新闻"""
        translated = []
        for i, item in enumerate(news_items):
            logger.info(f"Translating {i+1}/{len(news_items)}: {item.get('title', '')[:50]}...")
            translated_item = self.translate_news(item)
            translated.append(translated_item)
        return translated

    def _translate_zh_to_en(self, text: str) -> str:
        """翻译中文文本为英文"""
        if not text or not text.strip():
            return text
        try:
            prompt = f"""请将以下中文翻译为英文，保持原文的语气和专业术语：

{text}"""
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return self._get_text_from_response(message).strip()
        except Exception as e:
            logger.error(f"Translation error (zh->en): {e}")
            return text

    def _translate_html_zh_to_en(self, html_content: str) -> str:
        """翻译中文 HTML 内容为英文，保留 HTML 标签"""
        if not html_content:
            return html_content
        if not re.search(r'<[^>]+>', html_content):
            return self._translate_zh_to_en(html_content)
        try:
            prompt = f"""请将以下 HTML 内容翻译为英文。请：
1. 翻译所有可见文本为英文
2. 保留所有 HTML 标签和结构不变
3. 保持原文的格式和布局

HTML 内容：
{html_content}"""
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return self._get_text_from_response(message).strip()
        except Exception as e:
            logger.error(f"HTML translation error (zh->en): {e}")
            return self._translate_zh_to_en(html_content)

    def translate_news_zh_to_en(self, news_item: Dict[str, Any]) -> Dict[str, Any]:
        """翻译单条中文新闻为英文，中文原文保留，英文存入 _en 字段"""
        try:
            title = news_item.get('title', '')
            content = news_item.get('content', news_item.get('description', ''))

            title_en = self._translate_zh_to_en(title) if title else ''
            content_en = self._translate_html_zh_to_en(content) if content else ''

            result = {
                **news_item,
                'title': title,
                'content': content,
            }
            if title_en:
                result['title_en'] = title_en
            if content_en:
                result['content_en'] = content_en

            description = news_item.get('description', '')
            if description and description != content:
                # description 与 content 不同，单独翻译
                description_en = self._translate_zh_to_en(description) if description else ''
                if description_en:
                    result['description_en'] = description_en

            return result
        except Exception as e:
            logger.error(f"Error translating news (zh->en): {e}")
            return news_item

    def translate_batch_zh_to_en(self, news_items: list) -> list:
        """批量翻译中文新闻为英文"""
        translated = []
        for i, item in enumerate(news_items):
            logger.info(f"Translating zh->en {i+1}/{len(news_items)}: {item.get('title', '')[:50]}...")
            translated_item = self.translate_news_zh_to_en(item)
            translated.append(translated_item)
        return translated