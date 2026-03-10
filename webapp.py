"""小果新闻 Web 应用

提供前端页面和新闻数据 API，从 news 目录读取已保存的 HTML 新闻文件。
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, abort

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 新闻根目录
NEWS_DIR = Path(__file__).parent / "news"


def _parse_news_html(file_path: Path) -> Optional[dict]:
    """从新闻 HTML 文件中提取标题、内容和元数据。

    Args:
        file_path: HTML 文件路径

    Returns:
        包含 title, content, source, date, link 的字典，解析失败返回 None
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        logger.warning("无法读取文件: %s", file_path)
        return None

    # 提取标题（可能跨多行，需清理翻译注释等杂质）
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
        # 清理 markdown 标记和翻译注释
        title = re.sub(r"\*\*.*?\*\*", "", title)  # 去除 **...**
        title = re.sub(r"---.*", "", title, flags=re.DOTALL)  # 去除 --- 及后续说明
        title = re.sub(r"[（(]或[：:].*", "", title, flags=re.DOTALL)  # 去除（或：...）备选翻译
        title = re.sub(r"\s*-\s*\".*", "", title)  # 去除 - "注释..." 部分
        title = re.sub(r"\s+", " ", title).strip()  # 合并空白
        # 清理标题开头的标点和翻译标记
        title = re.sub(r"^[：:\s]+", "", title)
    else:
        title = file_path.stem

    # 提取来源标签
    source_match = re.search(r'class="source-tag"[^>]*>(.*?)</span>', text, re.DOTALL)
    source = source_match.group(1).strip() if source_match else ""

    # 提取日期
    date_match = re.search(r'class="date"[^>]*>(.*?)</div>', text, re.DOTALL)
    date_text = date_match.group(1).strip() if date_match else ""

    # 提取原文链接
    link_match = re.search(r'class="original-link".*?href="([^"]*)"', text, re.DOTALL)
    link = link_match.group(1) if link_match else ""

    # 提取正文内容
    content_match = re.search(
        r'<div class="content">(.*?)</div>\s*</div>\s*</body>',
        text,
        re.DOTALL,
    )
    content = content_match.group(1).strip() if content_match else ""

    return {
        "title": title,
        "content": content,
        "source": source,
        "date": date_text,
        "link": link,
        "filename": file_path.name,
    }


def _get_available_dates() -> list[str]:
    """获取所有可用的新闻日期，按降序排列。

    扫描所有新闻源目录，汇总去重后排序。

    Returns:
        日期字符串列表，如 ['2026-03-09', '2026-03-08', ...]
    """
    dates = set()
    # 扫描 kagi/science, kagi/tech, idaily
    for source_path in [
        NEWS_DIR / "kagi" / "science",
        NEWS_DIR / "kagi" / "tech",
        NEWS_DIR / "idaily",
    ]:
        if source_path.is_dir():
            for d in source_path.iterdir():
                if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name):
                    dates.add(d.name)
    return sorted(dates, reverse=True)


def _get_news_for_date(date: str) -> dict:
    """获取指定日期的所有新闻。

    Args:
        date: 日期字符串，如 '2026-03-09'

    Returns:
        按分类组织的新闻数据字典
    """
    result = {"date": date, "science": [], "tech": [], "idaily": []}

    # 分类目录映射
    categories = {
        "science": NEWS_DIR / "kagi" / "science" / date,
        "tech": NEWS_DIR / "kagi" / "tech" / date,
        "idaily": NEWS_DIR / "idaily" / date,
    }

    for category, dir_path in categories.items():
        if not dir_path.is_dir():
            continue
        for html_file in sorted(dir_path.glob("*.html")):
            # 只保留包含中文字符的文件（跳过纯英文版本）
            if not re.search(r"[\u4e00-\u9fff]", html_file.stem):
                continue
            article = _parse_news_html(html_file)
            if article:
                result[category].append(article)

    return result


# ── 页面路由 ──────────────────────────────────────────


@app.route("/")
def index():
    """首页：应用入口。"""
    return render_template("index.html")


@app.route("/news")
def news_page():
    """热点新闻页面。"""
    return render_template("news.html")


# ── API 路由 ──────────────────────────────────────────


@app.route("/api/dates")
def api_dates():
    """返回所有可用日期列表。"""
    dates = _get_available_dates()
    return jsonify({"dates": dates})


@app.route("/api/news/<date>")
def api_news(date: str):
    """返回指定日期的新闻数据。

    Args:
        date: 日期字符串，格式 YYYY-MM-DD
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        abort(400, "日期格式错误，应为 YYYY-MM-DD")

    data = _get_news_for_date(date)
    return jsonify(data)


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3010, debug=True)
