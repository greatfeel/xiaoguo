"""小果新闻 Web 应用

提供前端页面和新闻数据 API，从 news 目录读取已保存的 HTML 新闻文件。
"""

import os
import re
import json
import asyncio
import sqlite3
import logging
import random
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from flask import Flask, jsonify, render_template, abort, redirect, request, Response, send_from_directory

from tts_generator import TTSGenerator as _TTSGenerator

# 延迟初始化，配置加载后再创建
_tts_gen: "_TTSGenerator | None" = None

from translator import Translator
from saver import HTMLSaver

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 新闻根目录
NEWS_DIR = Path(__file__).parent / "news"

# 任务数据库路径
DB_PATH = Path(__file__).parent / "tasks.db"
CONFIG_PATH = Path(__file__).parent / "config.yaml"

# 作文题目文件路径
ESSAY_XLS_PATH = Path(__file__).parent / "高考作文题目汇总.xls"
ESSAY_JSON_PATH = Path(__file__).parent / "高考作文题目汇总.json"


def _load_config() -> dict:
    """加载配置文件并替换环境变量。"""
    if not CONFIG_PATH.exists():
        return {
            "ANTHROPIC_MODEL": "claude-sonnet-4-20250514",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_AUTH_TOKEN": "${ANTHROPIC_API_KEY}",
            "OUTPUT_DIR": "news",
        }

    config_str = CONFIG_PATH.read_text(encoding="utf-8")
    for key, value in os.environ.items():
        config_str = config_str.replace(f"${{{key}}}", value)
    return yaml.safe_load(config_str) or {}


# 初始化环境变量与配置
load_dotenv()
APP_CONFIG = _load_config()
try:
    _tts_gen = _TTSGenerator(APP_CONFIG)
except Exception as _tts_init_err:
    logger.warning("TTSGenerator 初始化失败，TTS 功能不可用: %s", _tts_init_err)
    _tts_gen = None
_HTML_SAVER = HTMLSaver(APP_CONFIG)
_TRANSLATOR: Optional[Translator] = None
_TRANSLATOR_INIT_FAILED = False


def _init_db():
    """Initialize tasks table if not exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            priority INTEGER DEFAULT 2 CHECK(priority IN (1, 2, 3)),
            completed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# Initialize on startup
_init_db()


def _contains_chinese(text: str) -> bool:
    """判断文本是否包含中文字符。"""
    return bool(text and re.search(r"[\u4e00-\u9fff]", text))


def _get_translator() -> Optional[Translator]:
    """惰性初始化翻译器，避免启动时阻塞。"""
    global _TRANSLATOR, _TRANSLATOR_INIT_FAILED

    if _TRANSLATOR is not None:
        return _TRANSLATOR
    if _TRANSLATOR_INIT_FAILED:
        return None

    try:
        _TRANSLATOR = Translator(APP_CONFIG)
        return _TRANSLATOR
    except Exception as exc:
        logger.warning("翻译器初始化失败，将跳过英文补全: %s", exc)
        _TRANSLATOR_INIT_FAILED = True
        return None


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

    # 提取页面语言标记
    lang_match = re.search(r'<html[^>]*lang="([^"]+)"', text, re.DOTALL)
    html_lang = lang_match.group(1).strip().lower() if lang_match else ""

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
        "html_lang": html_lang,
    }


def _detect_article_lang(article: dict) -> str:
    """基于页面标记和内容特征识别语言。"""
    filename = article.get("filename", "")
    if filename.endswith("_en.html"):
        return "en"

    html_lang = article.get("html_lang", "")
    if html_lang.startswith("en"):
        return "en"
    if html_lang.startswith("zh"):
        # 历史数据里 lang 可能始终是 zh-CN，需继续用文本判断兜底
        pass

    title = article.get("title", "")
    content = article.get("content", "")
    if _contains_chinese(title) or _contains_chinese(content):
        return "zh"
    return "en"


def _article_group_key(file_path: Path, article: dict) -> str:
    """生成中英配对分组键，优先使用原文链接。"""
    link = (article.get("link") or "").strip()
    if link:
        return f"link::{link}"

    stem = file_path.stem
    if stem.endswith("_en"):
        stem = stem[:-3]
    return f"file::{stem}"


def _write_english_cache(zh_file: Path, article_en: dict, source: str, date: str):
    """将英文翻译结果缓存为 _en.html，减少重复翻译。"""
    try:
        en_file = zh_file.with_name(f"{zh_file.stem}_en.html")
        if en_file.exists():
            return

        en_item = {
            "title": article_en.get("title_en") or article_en.get("title") or "",
            "content": article_en.get("content_en") or article_en.get("content") or "",
            "link": article_en.get("link", ""),
        }
        html = _HTML_SAVER._generate_html(en_item, source, date, lang="en")
        en_file.write_text(html, encoding="utf-8")
    except Exception as exc:
        logger.warning("英文缓存写入失败 %s: %s", zh_file, exc)


def _try_translate_idaily_to_en(dir_path: Path, article: dict, date: str) -> dict:
    """为 iDaily 中文文章补齐英文内容。"""
    if article.get("title_en") and article.get("content_en"):
        return article

    translator = _get_translator()
    if translator is None:
        return article

    try:
        translated = translator.translate_news_zh_to_en({
            "title": article.get("title", ""),
            "content": article.get("content", ""),
            "description": article.get("content", ""),
            "link": article.get("link", ""),
        })

        title_en = translated.get("title_en", "")
        content_en = translated.get("content_en", "")
        if not title_en or not content_en:
            return article

        article["title_en"] = title_en
        article["content_en"] = content_en

        zh_filename = article.get("filename")
        if zh_filename:
            zh_file = dir_path / zh_filename
            if zh_file.exists():
                _write_english_cache(zh_file, article, "idaily", date)

        return article
    except Exception as exc:
        logger.warning("iDaily 英文翻译失败: %s", exc)
        return article


def _date_has_news(date: str) -> bool:
    """检查某天是否存在可展示的新闻。"""
    for source_path in [
        NEWS_DIR / "kagi" / "science" / date,
        NEWS_DIR / "kagi" / "tech" / date,
        NEWS_DIR / "idaily" / date,
    ]:
        if source_path.is_dir():
            primary_files = [
                f for f in source_path.glob("*.html")
                if not f.stem.endswith("_en")
            ]
            if primary_files:
                return True
    return False


def _get_available_dates(only_with_news: bool = False) -> list[str]:
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
    sorted_dates = sorted(dates, reverse=True)
    if not only_with_news:
        return sorted_dates
    return [d for d in sorted_dates if _date_has_news(d)]


def _find_date_with_news(start_date: str = None) -> Optional[str]:
    """从指定日期开始往前找，第一个有新闻的日期。

    Args:
        start_date: 起始日期，默认今天

    Returns:
        第一个有新闻的日期字符串，如果没有则返回 None
    """
    from datetime import datetime

    if start_date is None:
        start_date = datetime.now().strftime('%Y-%m-%d')

    dates = _get_available_dates()
    if not dates:
        return None

    # 从最新的日期开始找
    for date in dates:
        if date > start_date:
            continue

        if _date_has_news(date):
            return date

    return None


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

        files = sorted(dir_path.glob("*.html"))
        grouped: dict[str, dict] = {}
        order: list[str] = []

        for html_file in files:
            article = _parse_news_html(html_file)
            if not article:
                continue

            key = _article_group_key(html_file, article)
            if key not in grouped:
                grouped[key] = {"zh": None, "en": None}
                order.append(key)

            lang = _detect_article_lang(article)
            if lang == "en":
                grouped[key]["en"] = article
            else:
                grouped[key]["zh"] = article

        for key in order:
            pair = grouped[key]
            zh_article = pair.get("zh")
            en_article = pair.get("en")

            # 优先展示中文结构，确保已有清洗逻辑稳定。
            base = zh_article or en_article
            if not base:
                continue

            merged = {
                "title": (zh_article or en_article).get("title", ""),
                "content": (zh_article or en_article).get("content", ""),
                "source": (zh_article or en_article).get("source", ""),
                "date": (zh_article or en_article).get("date", ""),
                "link": (zh_article or en_article).get("link", ""),
                "filename": (zh_article or en_article).get("filename", ""),
            }

            if en_article:
                merged["title_en"] = en_article.get("title", "")
                merged["content_en"] = en_article.get("content", "")

            # 英文单文件也允许展示，中文兜底为英文。
            if not zh_article and en_article:
                merged["title"] = en_article.get("title", "")
                merged["content"] = en_article.get("content", "")

            if category == "idaily":
                merged = _try_translate_idaily_to_en(dir_path, merged, date)

            # 注入预生成音频 URL（如果 MP3 文件已存在）
            zh_stem = Path(merged["filename"]).stem
            zh_mp3 = dir_path / f"{zh_stem}_zh.mp3"
            en_mp3 = dir_path / f"{zh_stem}_en.mp3"
            rel_dir = dir_path.relative_to(NEWS_DIR)
            if zh_mp3.exists():
                merged["audio_url_zh"] = f"/news-audio/{rel_dir}/{zh_stem}_zh.mp3"
            if en_mp3.exists():
                merged["audio_url_en"] = f"/news-audio/{rel_dir}/{zh_stem}_en.mp3"

            result[category].append(merged)

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


@app.route("/news-audio/<path:filepath>")
def news_audio(filepath: str):
    """服务预生成的 TTS MP3 文件（静态）。"""
    return send_from_directory(NEWS_DIR, filepath, mimetype="audio/mpeg")


# ── API 路由 ──────────────────────────────────────────


@app.route("/api/dates")
def api_dates():
    """返回所有有新闻内容的可用日期列表。"""
    dates = _get_available_dates(only_with_news=True)
    return jsonify({"dates": dates})


@app.route("/api/news/<date>")
def api_news(date: str):
    """返回指定日期的新闻数据，如果该日期无新闻则往前找最近的日期。"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        abort(400, "日期格式错误，应为 YYYY-MM-DD")

    # 尝试获取指定日期的新闻
    data = _get_news_for_date(date)

    # 检查是否有新闻，如果没有则往前找
    has_news = any([data.get("science"), data.get("tech"), data.get("idaily")])

    if not has_news:
        # 往前找最近的日期
        actual_date = _find_date_with_news(date)
        if actual_date and actual_date != date:
            data = _get_news_for_date(actual_date)
            data["date"] = actual_date
            data["actual_date"] = actual_date
        elif actual_date is None:
            # 没有任何新闻
            data["date"] = date
            data["actual_date"] = date
    else:
        data["date"] = date
        data["actual_date"] = date

    data["requested_date"] = date
    return jsonify(data)


@app.route("/api/tts", methods=["POST"])
def api_tts():
    """将文本转为音频（Edge TTS），命中磁盘缓存则直接返回。"""
    if _tts_gen is None:
        return jsonify({"error": "TTS 不可用"}), 503

    payload = request.get_json(silent=True) or {}
    text = _TTSGenerator.normalize_text(payload.get("text", ""))
    lang = payload.get("lang", "zh")
    style = payload.get("style", "standard")
    if lang not in ["zh", "en"]:
        lang = "zh"

    if not text:
        return jsonify({"error": "文本不能为空"}), 400

    audio_bytes = _tts_gen.synthesize_with_cache(text, lang, style)
    if not audio_bytes:
        return jsonify({"error": "TTS 生成失败"}), 500

    return Response(
        audio_bytes,
        mimetype="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


# ── 任务 API 路由 ────────────────────────────────────────


@app.route("/api/tasks", methods=["GET"])
def api_tasks_get():
    """获取所有任务，按截止日期和优先级排序。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT * FROM tasks
        ORDER BY
            CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END,
            due_date ASC,
            priority DESC,
            created_at DESC
    """)
    tasks = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify({"tasks": tasks})


@app.route("/api/tasks", methods=["POST"])
def api_tasks_create():
    """创建新任务。"""
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "标题不能为空"}), 400

    title = data.get("title", "")
    description = data.get("description", "")
    due_date = data.get("due_date", "")
    priority = data.get("priority", 2)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        INSERT INTO tasks (title, description, due_date, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (title, description, due_date, priority))
    task_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"id": task_id, "message": "Task created"}), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_tasks_update(task_id: int):
    """更新任务。"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效数据"}), 400

    # Build dynamic update query
    allowed_fields = ["title", "description", "due_date", "priority", "completed"]
    updates = []
    values = []

    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            values.append(data[field])

    if not updates:
        return jsonify({"error": "没有要更新的字段"}), 400

    updates.append("updated_at = datetime('now')")
    values.append(task_id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()

    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404

    conn.close()
    return jsonify({"message": "Task updated"})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_tasks_delete(task_id: int):
    """删除任务。"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()

    if cur.rowcount == 0:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404

    conn.close()
    return jsonify({"message": "Task deleted"})


# ── 作文 API 路由 ──────────────────────────────────────────


def _load_essay_questions():
    """从 XLS 文件加载作文题目，支持 pandas 和 xlrd 回退。"""
    def _normalize_header(value: object) -> str:
        """标准化表头，去除空白与常见分隔符。"""
        text = str(value or "").strip().lower()
        return re.sub(r"[\s_\-]+", "", text)

    def _normalize_cell(value: object) -> str:
        """标准化单元格内容，过滤空值与 NaN。"""
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() == "nan" else text

    def _select_columns_from_headers(headers: list[str]) -> tuple[Optional[str], Optional[str]]:
        """根据表头名称挑选题目标题列和题目内容列。"""
        title_aliases = {
            "题目标题", "标题", "作文题目", "题目", "题干标题", "标题名称", "topic", "title"
        }
        content_aliases = {
            "题目内容", "内容", "作文内容", "题干", "材料", "题目描述", "description", "content"
        }

        title_col = None
        content_col = None
        normalized_map = {_normalize_header(h): h for h in headers}

        for alias in title_aliases:
            col = normalized_map.get(_normalize_header(alias))
            if col is not None:
                title_col = col
                break

        for alias in content_aliases:
            col = normalized_map.get(_normalize_header(alias))
            if col is not None:
                content_col = col
                break

        # 如果未匹配到标准列，回退到前两个非空列，降低因表头变化导致的读取失败。
        if title_col is None or content_col is None:
            non_empty = [h for h in headers if str(h).strip()]
            if len(non_empty) >= 2:
                title_col = title_col or non_empty[0]
                content_col = content_col or non_empty[1]

        return title_col, content_col

    questions = []

    def _load_from_json_fallback() -> list[dict]:
        """在 XLS 解析失败时从 JSON 兜底加载。"""
        if not ESSAY_JSON_PATH.exists():
            return []
        try:
            payload = json.loads(ESSAY_JSON_PATH.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                return []

            normalized = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                title = _normalize_cell(item.get("title", ""))
                content = _normalize_cell(item.get("content", ""))
                if title and content:
                    normalized.append({"title": title, "content": content})

            if normalized:
                logger.info("使用 JSON 兜底加载了 %d 道作文题目", len(normalized))
            return normalized
        except Exception as exc:
            logger.warning("JSON 兜底加载失败: %s", exc)
            return []

    if not ESSAY_XLS_PATH.exists():
        logger.warning(f"作文题目文件不存在: {ESSAY_XLS_PATH}")
        return _load_from_json_fallback()

    try:
        # 优先尝试使用 pandas
        import pandas as pd
        df = pd.read_excel(ESSAY_XLS_PATH)
        title_col, content_col = _select_columns_from_headers(df.columns.tolist())
        if title_col is None or content_col is None:
            logger.warning("pandas 未识别到有效列，尝试 xlrd 回退")
            raise ValueError("missing title/content columns")

        for _, row in df.iterrows():
            title_raw = row.get(title_col, "")
            content_raw = row.get(content_col, "")
            if pd.isna(title_raw) or pd.isna(content_raw):
                continue

            title = _normalize_cell(title_raw)
            content = _normalize_cell(content_raw)
            if title and content:
                questions.append({'title': title, 'content': content})
        logger.info(f"使用 pandas 加载了 {len(questions)} 道作文题目")
        if questions:
            return questions
        logger.warning("pandas 读取结果为空，尝试 JSON 兜底")
        return _load_from_json_fallback()
    except ImportError:
        pass  # pandas 未安装，使用 xlrd
    except Exception as e:
        logger.warning(f"pandas 加载失败，尝试 xlrd: {e}")

    try:
        # 回退到 xlrd
        import xlrd
        wb = xlrd.open_workbook(ESSAY_XLS_PATH)
        sheet = wb.sheet_by_index(0)

        # 查找列索引
        header_row = 0
        headers = [str(sheet.cell_value(header_row, col)).strip() for col in range(sheet.ncols)]
        title_name, content_name = _select_columns_from_headers(headers)
        title_col = headers.index(title_name) if title_name in headers else None
        content_col = headers.index(content_name) if content_name in headers else None

        if title_col is None or content_col is None:
            logger.warning("无法找到题目标题或题目内容列")
            return questions

        # 读取数据行
        for row in range(1, sheet.nrows):
            title = _normalize_cell(sheet.cell_value(row, title_col))
            content = _normalize_cell(sheet.cell_value(row, content_col))
            if title and content:
                questions.append({'title': title, 'content': content})

        logger.info(f"使用 xlrd 加载了 {len(questions)} 道作文题目")
        if questions:
            return questions
        logger.warning("xlrd 读取结果为空，尝试 JSON 兜底")
        return _load_from_json_fallback()

    except Exception as e:
        logger.error(f"加载作文题目失败: {e}")
        return _load_from_json_fallback()


# 加载作文题目（启动时预加载，运行时可自动重载）
_essay_questions = _load_essay_questions()


def _get_essay_questions(force_reload: bool = False) -> list[dict]:
    """获取作文题目列表；为空时自动重载，避免因启动时异常导致一直为空。"""
    global _essay_questions

    if force_reload or not _essay_questions:
        reloaded = _load_essay_questions()
        if reloaded:
            _essay_questions = reloaded
            logger.info("作文题目已重载，当前共 %d 条", len(_essay_questions))

    return _essay_questions


def _get_translator():
    """获取翻译器实例，用于调用大模型。"""
    config = _load_config()
    try:
        return Translator(config)
    except Exception as exc:
        logger.error(f"Translator init failed: {exc}")
        return None


@app.route("/essay")
def essay_page():
    """作文宝页面：作文提纲测试模块。"""
    return render_template("essay.html")


@app.route("/api/essay/random")
def api_essay_random():
    """随机抽取一道作文题目。"""
    questions = _get_essay_questions()
    if not questions:
        return jsonify({"error": "题目库为空"}), 500

    question = random.choice(questions)
    return jsonify({
        "title": question['title'],
        "content": question['content']
    })


@app.route("/api/essay/questions")
def api_essay_questions():
    """获取所有作文题目列表。"""
    return jsonify({"questions": _get_essay_questions()})


@app.route("/api/essay/reload", methods=["POST"])
def api_essay_reload():
    """手动重载作文题目。"""
    questions = _get_essay_questions(force_reload=True)
    if not questions:
        return jsonify({"error": "重载失败，题目库为空"}), 500

    return jsonify({"message": "重载成功", "count": len(questions)})


ESSAY_GRADING_PROMPT = '''你是一位资深高考作文阅卷老师。请对以下学生的作文大纲进行评分和点评。

作文题目：
{question_title}
{question_content}

学生提交的作文大纲：
{outline}

请以 10 分为基准进行评分，并给出详细评价。请按以下格式输出：

【得分】X.X/10

【评判意见】
- 优点：...
- 不足：...

【改进建议】
...

【参考大纲】
请提供一个优秀的大纲范例，结构参考：
一、引论（...）
二、本论（...）
三、结论（...）

请用中文回答，保持专业、客观、建设性的语气。'''


ESSAY_GENERATE_PROMPT = '''你是一位资深高考作文辅导老师。请根据以下作文题目，按照指定格式生成一篇议论文写作大纲。

作文题目：
{question_title}
{question_content}

请严格按照以下范例格式生成大纲：

议论文写作提纲（示例）：《谈意气》（2006湖南卷优秀作文）
一、引论（1）用雏鹰翱翔天宇、骏马驰骋万里引出中心论点：英雄创业靠的是舍我其谁勇战万方的勇气。（类比）
二、本论（2—7）分三层论证中心论点。
第一层（2-3）分论点1：舍我其谁的意气使人奋起。（例证、引证）
论据：李贺、陈胜、孟子豪言壮语（效果分析法）
第二层（4-5）分论点2：献身理想的意气使人勇敢。（例证、排比）
论据：布鲁诺、哥伦布、红军的事例（因果分析法）
第三层（6-7）分论点3：勇于探索的意气使人发挥潜力。（例证）
论据：杨振宁、李政道、吴剑雄、王淦昌（因果分析法）
三、结论（8）用浆、巨轮、彼岸作比归纳全文，激励人们。（比喻）

要求：
1. 严格按照上述格式：引论、本论（分三层）、结论
2. 每一层都要有分论点、论证方法和论据
3. 语言简洁有力，适合高考议论文
4. 只输出大纲内容，不要有任何额外说明

请直接输出生成的大纲：'''


@app.route("/api/essay/grade", methods=["POST"])
def api_essay_grade():
    """调用大模型对作文大纲进行评分。"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效请求"}), 400

    question_title = data.get("question_title", "")
    question_content = data.get("question_content", "")
    outline = data.get("outline", "")

    if not outline or not question_title:
        return jsonify({"error": "缺少必要参数"}), 400

    translator = _get_translator()
    if not translator:
        return jsonify({"error": "评分服务暂不可用"}), 503

    try:
        prompt = ESSAY_GRADING_PROMPT.format(
            question_title=question_title,
            question_content=question_content,
            outline=outline
        )

        message = translator.client.messages.create(
            model=translator.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        result = translator._get_text_from_response(message).strip()
        return jsonify({"result": result})

    except Exception as exc:
        logger.error(f"评分失败: {exc}")
        return jsonify({"error": f"评分失败: {str(exc)}"}), 500


@app.route("/api/essay/generate-outline", methods=["POST"])
def api_essay_generate_outline():
    """调用大模型生成作文大纲。"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "无效请求"}), 400

    question_title = data.get("question_title", "")
    question_content = data.get("question_content", "")

    if not question_title:
        return jsonify({"error": "缺少题目信息"}), 400

    translator = _get_translator()
    if not translator:
        return jsonify({"error": "AI 服务暂不可用"}), 503

    try:
        prompt = ESSAY_GENERATE_PROMPT.format(
            question_title=question_title,
            question_content=question_content
        )

        message = translator.client.messages.create(
            model=translator.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        result = translator._get_text_from_response(message).strip()
        return jsonify({"outline": result})

    except Exception as exc:
        logger.error(f"大纲生成失败: {exc}")
        return jsonify({"error": f"大纲生成失败: {str(exc)}"}), 500


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=3010, debug=True)
