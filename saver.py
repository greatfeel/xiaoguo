"""
HTML Saver Module
将新闻保存为 HTML 文件
"""
import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class HTMLSaver:
    """HTML 文件保存器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_dir = config.get('OUTPUT_DIR', 'news')
        self.date_format = config.get('DATE_FORMAT', '%Y-%m-%d')

    def save_news(self, news_item: Dict[str, Any], source: str, date: str = None) -> str:
        """保存单条新闻为 HTML 文件，如有双语字段则同时保存英文版"""
        if date is None:
            date = news_item.get('published', datetime.now().strftime(self.date_format))

        # 创建目录
        dir_path = os.path.join(self.output_dir, source, date)
        os.makedirs(dir_path, exist_ok=True)

        # 生成文件名（使用标题的拼音或slug）
        title = news_item.get('title', '')
        filename = self._generate_filename(title)
        file_path = os.path.join(dir_path, f"{filename}.html")

        # 生成 HTML 内容
        html_content = self._generate_html(news_item, source, date)

        # 保存文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Saved: {file_path}")

        # 如果有英文版本，保存 _en.html
        title_en = news_item.get('title_en', '')
        content_en = news_item.get('content_en', '')
        if title_en and content_en:
            en_item = {**news_item, 'title': title_en, 'content': content_en}
            en_filename = self._generate_filename(title_en)
            en_file_path = os.path.join(dir_path, f"{en_filename}_en.html")
            en_html = self._generate_html(en_item, source, date)
            with open(en_file_path, 'w', encoding='utf-8') as f:
                f.write(en_html)
            logger.info(f"Saved English version: {en_file_path}")

        return file_path

    def save_batch(self, news_items: List[Dict[str, Any]], source: str, date: str = None) -> List[str]:
        """批量保存新闻"""
        if not news_items:
            return []

        if date is None:
            date = news_items[0].get('published', datetime.now().strftime(self.date_format))

        saved_files = []
        for item in news_items:
            try:
                file_path = self.save_news(item, source, date)
                saved_files.append(file_path)
            except Exception as e:
                logger.error(f"Error saving news: {e}")

        logger.info(f"Saved {len(saved_files)} files to {source}/{date}")
        return saved_files

    def _generate_filename(self, title: str) -> str:
        """从标题生成文件名"""
        if not title:
            return f"news_{datetime.now().strftime('%H%M%S')}"

        # 移除非ASCII字符
        slug = re.sub(r'[^\w\s-]', '', title)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')[:50]  # 限制长度

        return slug or f"news_{datetime.now().strftime('%H%M%S')}"

    def _generate_html(self, news_item: Dict[str, Any], source: str, date: str) -> str:
        """生成新闻 HTML 页面"""
        title = news_item.get('title', '无标题')
        content = news_item.get('content', news_item.get('description', ''))
        link = news_item.get('link', '')

        # 清理内容中的HTML标签，只保留基本格式
        cleaned_content = self._clean_html(content)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.8;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }}
        .source-tag {{
            display: inline-block;
            background: #007bff;
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        .date {{
            color: #999;
            font-size: 14px;
            margin-top: 10px;
        }}
        h1 {{
            font-size: 28px;
            line-height: 1.4;
            color: #222;
            margin-bottom: 15px;
        }}
        .original-link {{
            margin-top: 15px;
        }}
        .original-link a {{
            color: #007bff;
            text-decoration: none;
            font-size: 14px;
        }}
        .original-link a:hover {{
            text-decoration: underline;
        }}
        .content {{
            font-size: 16px;
            line-height: 1.8;
        }}
        .content p {{
            margin-bottom: 1.5em;
        }}
        .content img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .content a {{
            color: #007bff;
        }}
        .content h2, .content h3, .content h4 {{
            margin: 1.5em 0 0.5em;
            color: #222;
        }}
        .content ul, .content ol {{
            margin: 1em 0;
            padding-left: 2em;
        }}
        .content blockquote {{
            border-left: 4px solid #ddd;
            padding-left: 1em;
            margin: 1em 0;
            color: #666;
        }}
        .content pre, .content code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 14px;
        }}
        .content pre {{
            padding: 15px;
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="source-tag">{source}</span>
            <h1>{title}</h1>
            <div class="date">发布日期: {date}</div>
            <div class="original-link">
                <a href="{link}" target="_blank" rel="noopener">查看原文 →</a>
            </div>
        </div>
        <div class="content">
            {cleaned_content}
        </div>
    </div>
</body>
</html>"""
        return html

    def _clean_html(self, content: str) -> str:
        """清理 HTML 内容，保留基本格式"""
        if not content:
            return ''

        # 如果没有 HTML 标签，直接返回
        if not re.search(r'<[^>]+>', content):
            # 段落分隔
            paragraphs = content.split('\n\n')
            return ''.join(f'<p>{p.strip()}</p>' for p in paragraphs if p.strip())

        # 保留常见的 HTML 标签
        allowed_tags = ['p', 'br', 'b', 'strong', 'i', 'em', 'u', 'a', 'img',
                       'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                       'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
                       'table', 'thead', 'tbody', 'tr', 'th', 'td']

        # 处理图片
        content = re.sub(r'<img([^>]*)>', r'<img\1 />', content)

        return content