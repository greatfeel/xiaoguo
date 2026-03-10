"""
RSS News Fetcher Module
抓取 Kagi RSS 和 iDaily 新闻源
"""
import re
import feedparser
import requests
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class RSSFetcher:
    """RSS 新闻抓取器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.timeout = config.get('TIMEOUT', 30)

    def fetch_kagi_rss(self, url: str) -> List[Dict[str, Any]]:
        """抓取 Kagi RSS 源

        使用 feed 级别的 lastBuildDate 作为存储日期，而不是单个条目的 pubDate。
        这样所有同一天的新闻会存储在同一个日期目录下。
        """
        logger.info(f"Fetching Kagi RSS: {url}")

        try:
            feed = feedparser.parse(url)

            if not feed.entries:
                logger.warning(f"No entries found in {url}")
                return []

            # 获取 feed 级别的 lastBuildDate 作为存储日期
            feed_date = self._parse_date(feed.feed.get('updated', ''))
            logger.info(f"Kagi RSS feed lastBuildDate: {feed_date}")

            news_items = []
            for entry in feed.entries:
                # 使用 feed 级别的日期，而非单个条目的 pubDate
                published = feed_date

                item = {
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'description': entry.get('summary', entry.get('description', '')),
                    'content': self._extract_content(entry),
                    'published': published,
                    'source': 'kagi',
                }

                # 添加额外字段
                if hasattr(entry, 'author'):
                    item['author'] = entry.author
                if hasattr(entry, 'tags'):
                    item['tags'] = [tag.term for tag in entry.tags]

                news_items.append(item)

            logger.info(f"Fetched {len(news_items)} items from Kagi RSS")
            return news_items

        except Exception as e:
            logger.error(f"Error fetching Kagi RSS {url}: {e}")
            return []

    def fetch_idaily(self, url: str) -> List[Dict[str, Any]]:
        """抓取 iDaily RSS 源"""
        logger.info(f"Fetching iDaily: {url}")

        try:
            feed = feedparser.parse(url)

            if not feed.entries:
                logger.warning(f"No entries found in iDaily feed")
                return []

            news_items = []
            for entry in feed.entries:
                # 解析日期
                published = self._parse_date(entry.get('published', ''))

                # 提取封面图片（从 enclosure 或 description 中的 img 标签）
                image = ''
                if hasattr(entry, 'enclosures') and entry.enclosures:
                    image = entry.enclosures[0].get('href', '')

                # 清理标题中的日期后缀（如 " - March 7, 2026"）
                title = entry.get('title', '')
                title = re.sub(r'\s*-\s*\w+\s+\d{1,2},\s*\d{4}\s*$', '', title)

                news_item = {
                    'title': title,
                    'link': entry.get('link', ''),
                    'description': entry.get('summary', ''),
                    'content': self._extract_content(entry),
                    'published': published,
                    'source': 'idaily',
                    'image': image,
                }
                news_items.append(news_item)

            logger.info(f"Fetched {len(news_items)} items from iDaily")
            return news_items

        except Exception as e:
            logger.error(f"Error fetching iDaily {url}: {e}")
            return []

    def _extract_content(self, entry) -> str:
        """从 RSS 条目中提取内容"""
        # 优先使用 content
        if hasattr(entry, 'content'):
            for content in entry.content:
                if content.type == 'text/html' or content.type == 'html':
                    return content.value
                # 如果没有 HTML 类型，使用第一个
                return content.value

        # 其次使用 summary
        if hasattr(entry, 'summary'):
            return entry.summary

        return ''

    def _parse_date(self, date_str: str) -> str:
        """解析日期字符串"""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')

        try:
            parsed = date_parser.parse(date_str)
            return parsed.strftime('%Y-%m-%d')
        except Exception:
            return datetime.now().strftime('%Y-%m-%d')

    def get_today_news(self, news_items: List[Dict[str, Any]], target_date: str = None) -> List[Dict[str, Any]]:
        """获取指定日期或最近一天的新闻

        Args:
            news_items: 新闻列表
            target_date: 目标日期 (YYYY-MM-DD)，默认为今天
        """
        if not news_items:
            return []

        if target_date is None:
            target_date = datetime.now().strftime('%Y-%m-%d')

        # 优先返回目标日期的新闻
        date_news = [item for item in news_items if item.get('published') == target_date]
        if date_news:
            return date_news

        # 如果没有目标日期的新闻，返回最近一天的新闻
        sorted_items = sorted(
            news_items,
            key=lambda x: x.get('published', ''),
            reverse=True
        )

        if sorted_items:
            latest_date = sorted_items[0].get('published')
            logger.info(f"No news for {target_date}, using latest: {latest_date}")
            return [item for item in sorted_items if item.get('published') == latest_date]

        return news_items