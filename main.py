#!/usr/bin/env python3
"""
RSS News Fetcher Main Program
每日抓取 RSS 新闻并保存为 HTML
"""
import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List
import yaml
from dotenv import load_dotenv

from pathlib import Path
from fetcher import RSSFetcher
from translator import Translator
from saver import HTMLSaver
from tts_generator import TTSGenerator


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """加载配置文件"""
    if not os.path.exists(config_path):
        # 使用默认配置
        return {
            'ANTHROPIC_MODEL': 'claude-sonnet-4-20250514',
            'ANTHROPIC_BASE_URL': 'https://api.anthropic.com',
            'ANTHROPIC_AUTH_TOKEN': '${ANTHROPIC_API_KEY}',
            'SOURCES': {
                'kagi': {
                    'science': 'https://news.kagi.com/science.xml',
                    'tech': 'https://news.kagi.com/tech.xml',
                },
                'idaily': {
                    'url': 'https://plink.anyfeeder.com/idaily/today',
                }
            },
            'OUTPUT_DIR': 'news',
            'DATE_FORMAT': '%Y-%m-%d',
            'TIMEOUT': 30,
        }

    with open(config_path, 'r', encoding='utf-8') as f:
        # 替换环境变量
        config_str = f.read()
        for key, value in os.environ.items():
            config_str = config_str.replace(f'${{{key}}}', value)

        return yaml.safe_load(config_str)


def process_source(
    fetcher: RSSFetcher,
    translator: Translator,
    saver: HTMLSaver,
    url: str,
    source: str,
    source_type: str,
    date: str = None,
    need_translate: bool = True,
    translate_to_en: bool = False,
    tts_gen=None,
) -> int:
    """处理单个新闻源，逐条处理并立即保存。

    对每条新闻依次执行：
      1. 保存原始文章（新文章），并立即生成原文 MP3
      2. 翻译并保存（kagi en→zh），翻译后立即生成 zh/en MP3
      3. 翻译并保存（idaily zh→en），检测缺失的 MP3 并立即生成
    已完成的步骤均为幂等，重复运行可补全遗漏的翻译或 MP3。
    """
    logger = logging.getLogger(__name__)

    # 抓取新闻
    if source_type == 'kagi':
        news_items = fetcher.fetch_kagi_rss(url)
    elif source_type == 'idaily':
        news_items = fetcher.fetch_idaily(url)
    else:
        logger.warning(f"Unknown source type: {source_type}")
        return 0

    if not news_items:
        logger.warning(f"No news fetched from {source}")
        return 0

    # 获取指定日期或最近一天的新闻
    today_news = fetcher.get_today_news(news_items, target_date=date)
    if not today_news:
        logger.warning(f"No recent news found for {source}")
        return 0

    # 使用实际新闻日期作为保存目录日期
    actual_date = today_news[0].get('published', date)
    dir_obj = Path(saver.output_dir) / source / actual_date
    dir_obj.mkdir(parents=True, exist_ok=True)
    logger.info(f"Processing {len(today_news)} news items for {actual_date}")

    saved_count = 0

    for item in today_news:
        filename = saver._generate_filename(item.get('title', ''))
        file_path = dir_obj / f"{filename}.html"
        en_file_path = dir_obj / f"{filename}_en.html"
        article_exists = file_path.exists() or en_file_path.exists()

        # ── 步骤1：保存原始文章（新文章），立即生成 MP3 ──────────────
        if not article_exists:
            try:
                saver.save_news(item, source, actual_date)
                saved_count += 1
                logger.info(f"已保存: {filename}")
            except Exception as e:
                logger.error(f"保存失败 {filename}: {e}")
                continue

            # 立即为原始文章生成 MP3
            if tts_gen is not None:
                orig_lang = 'en' if need_translate else 'zh'
                tts_gen.generate_article_audio(
                    title=item.get('title', ''),
                    content=item.get('content', ''),
                    lang=orig_lang,
                    output_path=dir_obj / f"{filename}_{orig_lang}.mp3",
                )
        else:
            logger.info(f"文章已存在: {filename}")

        # ── 步骤2：kagi (en→zh) 翻译，翻译后立即生成 MP3 ────────────
        # en_file_path（{filename}_en.html）由 saver 在翻译保存时创建，
        # 存在则说明翻译已完成，不再重复翻译。
        if translator is not None and need_translate:
            if not en_file_path.exists():
                try:
                    translated = translator.translate_news(item)
                    if translated:
                        saver.save_news(translated, source, actual_date)
                        logger.info(f"已保存翻译: {filename}")
                        if tts_gen is not None:
                            zh_stem = saver._generate_filename(translated.get('title', ''))
                            tts_gen.generate_article_audio(
                                title=translated.get('title', ''),
                                content=translated.get('content', ''),
                                lang='zh',
                                output_path=dir_obj / f"{zh_stem}_zh.mp3",
                            )
                            tts_gen.generate_article_audio(
                                title=translated.get('title_en', ''),
                                content=translated.get('content_en', ''),
                                lang='en',
                                output_path=dir_obj / f"{zh_stem}_en.mp3",
                            )
                except Exception as e:
                    logger.error(f"翻译失败 {filename}: {e}")

        # ── 步骤3：idaily (zh→en) 翻译，检测缺失 MP3 并立即生成 ──────
        if translator is not None and translate_to_en:
            zh_stem = filename  # idaily: zh_stem 即原始中文文件名
            zh_mp3 = dir_obj / f"{zh_stem}_zh.mp3"
            en_mp3 = dir_obj / f"{zh_stem}_en.mp3"

            # 确保 zh MP3 存在
            if tts_gen is not None and not zh_mp3.exists():
                tts_gen.generate_article_audio(
                    title=item.get('title', ''),
                    content=item.get('content', ''),
                    lang='zh',
                    output_path=zh_mp3,
                )

            # en MP3 缺失则翻译并生成
            if not en_mp3.exists():
                try:
                    translated = translator.translate_news_zh_to_en(item)
                    if translated:
                        saver.save_news(translated, source, actual_date)
                        logger.info(f"已保存英文版: {filename}")
                        if tts_gen is not None:
                            tts_gen.generate_article_audio(
                                title=translated.get('title_en', ''),
                                content=translated.get('content_en', ''),
                                lang='en',
                                output_path=en_mp3,
                            )
                except Exception as e:
                    logger.error(f"翻译失败 {filename}: {e}")

    # 兜底：补全目录中已有 HTML 但仍缺少音频的条目（幂等）
    if tts_gen is not None:
        missing = tts_gen.generate_missing_for_dir(dir_obj)
        if missing > 0:
            logger.info(f"补全音频: {missing} 个")

    return saved_count


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='RSS News Fetcher - 每日抓取新闻并翻译保存'
    )
    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml)'
    )
    parser.add_argument(
        '-d', '--date',
        help='指定日期 (格式: YYYY-MM-DD, 默认: 今天)'
    )
    parser.add_argument(
        '-s', '--source',
        choices=['kagi', 'idaily', 'all'],
        default='all',
        help='指定新闻源 (默认: all)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    parser.add_argument(
        '--no-translate',
        action='store_true',
        help='不翻译，直接保存原文'
    )
    parser.add_argument(
        '--no-audio',
        action='store_true',
        help='不预生成 TTS 音频文件'
    )

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # 从 .env 文件加载环境变量（不覆盖已有的环境变量）
    load_dotenv()

    # 加载配置
    config = load_config(args.config)
    logger.info("Config loaded")

    # 确定日期
    date = args.date or datetime.now().strftime('%Y-%m-%d')
    logger.info(f"Using date: {date}")

    # 初始化模块
    fetcher = RSSFetcher(config)
    saver = HTMLSaver(config)

    # 如果需要翻译，初始化翻译器
    translator = None if args.no_translate else Translator(config)
    tts_gen = None if args.no_audio else TTSGenerator(config)

    total_saved = 0

    # 处理 Kagi 新闻源（英文，需要翻译）
    if args.source in ['all', 'kagi']:
        sources = config.get('SOURCES', {}).get('kagi', {})
        for key, url in sources.items():
            logger.info(f"Processing kagi/{key}...")
            count = process_source(
                fetcher, translator, saver,
                url, f'kagi/{key}', 'kagi', date,
                need_translate=True,
                tts_gen=tts_gen,
            )
            total_saved += count
            logger.info(f"Saved {count} files from kagi/{key}")

    # 处理 iDaily 新闻源（已是中文，无需翻译）
    if args.source in ['all', 'idaily']:
        sources = config.get('SOURCES', {}).get('idaily', {})
        url = sources.get('url', '')
        if url:
            logger.info("Processing idaily...")
            count = process_source(
                fetcher, translator, saver,
                url, 'idaily', 'idaily', date,
                need_translate=False,
                translate_to_en=(translator is not None),
                tts_gen=tts_gen,
            )
            total_saved += count
            logger.info(f"Saved {count} files from idaily")

    logger.info(f"Total saved: {total_saved} files")


if __name__ == '__main__':
    main()