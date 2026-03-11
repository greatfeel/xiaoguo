"""小果新闻 Web 应用

提供前端页面和新闻数据 API，从 news 目录读取已保存的 HTML 新闻文件。
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, abort, redirect

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


def _find_en_file(dir_path: Path, zh_files_sorted: list, zh_index: int) -> Optional[Path]:
    """查找与指定中文文件配对的英文版本文件（_en.html）。

    使用排序索引匹配，因为 saver 保持原始顺序保存中英文文件。

    Args:
        dir_path: 目录路径
        zh_files_sorted: 排序后的中文文件列表
        zh_index: 当前文件在 zh_files_sorted 中的索引

    Returns:
        英文版文件路径，不存在则返回 None
    """
    en_files = sorted(dir_path.glob("*_en.html"))
    if not en_files or zh_index >= len(en_files):
        return None
    return en_files[zh_index]


def _get_news_for_date(date: str) -> dict:
    """获取指定日期的所有新闻，包含双语字段。

    Args:
        date: 日期字符串，如 '2026-03-09'

    Returns:
        按分类组织的新闻数据字典，包含 title_en/content_en 字段（如果存在英文版）
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

        # 收集所有中文命名的文件，排序
        zh_files = sorted([
            f for f in dir_path.glob("*.html")
            if not f.stem.endswith("_en")
            and re.search(r"[\u4e00-\u9fff]", f.stem)
        ])

        for idx, html_file in enumerate(zh_files):
            article = _parse_news_html(html_file)
            if not article:
                continue

            # 尝试加载对应的英文版本
            en_file = _find_en_file(dir_path, zh_files, idx)
            if en_file:
                en_article = _parse_news_html(en_file)
                if en_article:
                    article['title_en'] = en_article['title']
                    article['content_en'] = en_article['content']

            result[category].append(article)

    return result


# ── 页面路由 ──────────────────────────────────────────


@app.route("/")
def index():
    """首页：应用入口。"""
    return render_template("index.html")


@app.route("/calendar")
def calendar_page():
    """高考日历页面：重定向到 Outlook 日历。

    由于 Outlook 日历 iframe 存在跨域和沙箱限制问题（crypto_nonexistent），
    无法在 iframe 中正常加载，改为直接重定向用户到 Outlook 日历页面。
    """
    return redirect("https://outlook.live.com/owa/calendar/26555a2a-43dc-4283-a125-ed904dea08e1/e0a7b3ff-bb52-4509-a9a2-c84ec7381e5b/cid-FF1DD0E83EAD4EF6/index.html", code=302)


@app.route("/tasks")
def tasks_page():
    """我的任务页面：嵌入 Notion 任务清单。"""
    return render_template("tasks.html")


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
