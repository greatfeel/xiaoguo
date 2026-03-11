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

from fetcher import RSSFetcher
from translator import Translator
from saver import HTMLSaver


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
) -> int:
    """处理单个新闻源

    Args:
        need_translate: 是否需要翻译（iDaily 已经是中文，不需要翻译）
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
    logger.info(f"Processing {len(today_news)} news items for {actual_date}")

    # 翻译英文新闻（iDaily 已经是中文，跳过翻译）
    if translator is not None and need_translate:
        # 先保存英文原文到 archives 目录
        archive_saver = HTMLSaver({**saver.config, 'OUTPUT_DIR': 'archives'})
        archive_saver.save_batch(today_news, source, actual_date)
        logger.info(f"Archived {len(today_news)} original articles")

        translated_news = translator.translate_batch(today_news)
    elif translator is not None and translate_to_en:
        # iDaily: 中文->英文，生成双语版本
        logger.info(f"Translating iDaily zh->en for {len(today_news)} items")
        translated_news = translator.translate_batch_zh_to_en(today_news)
    else:
        translated_news = today_news

    # 保存 HTML
    saved_files = saver.save_batch(translated_news, source, actual_date)

    return len(saved_files)


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

    total_saved = 0

    # 处理 Kagi 新闻源（英文，需要翻译）
    if args.source in ['all', 'kagi']:
        sources = config.get('SOURCES', {}).get('kagi', {})
        for key, url in sources.items():
            logger.info(f"Processing kagi/{key}...")
            count = process_source(
                fetcher, translator, saver,
                url, f'kagi/{key}', 'kagi', date,
                need_translate=True
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
                translate_to_en=(translator is not None)
            )
            total_saved += count
            logger.info(f"Saved {count} files from idaily")

    logger.info(f"Total saved: {total_saved} files")


if __name__ == '__main__':
    main()