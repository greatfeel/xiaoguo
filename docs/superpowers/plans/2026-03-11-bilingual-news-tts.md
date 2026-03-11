# Bilingual News Display + TTS Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bilingual EN/ZH tabs to all news cards and a TTS play/pause button per article.

**Architecture:** Backend generates paired `title.html` (primary language) + `title_en.html` (English) for all articles. Webapp serves both versions in JSON. Frontend renders tab switcher and TTS controls using Web Speech API.

**Tech Stack:** Python (Flask, Anthropic SDK), Vanilla JS, Web Speech API

---

## File Changes

| File | Change |
|------|--------|
| `translator.py` | Preserve originals as `title_en`/`content_en`; add `translate_news_zh_to_en()` + `translate_batch_zh_to_en()` |
| `saver.py` | Save `_en.html` alongside primary file when bilingual fields present |
| `main.py` | Enable iDaily translation (zh->en) via new `translate_to_en` flag |
| `webapp.py` | Load paired `_en.html` files; return `title_en`/`content_en` in JSON |
| `templates/news.html` | Tab switcher UI, TTS button, playback queue management |

---

## Chunk 1: Backend — translator.py + saver.py

### Task 1: translator.py — preserve originals + add zh->en direction

**File:** `translator.py`

Current `translate_news()` overwrites `title`/`content`. We need to:
1. Preserve originals as `title_en`/`content_en` before overwriting (for Kagi)
2. Add `translate_news_zh_to_en()` for iDaily (Chinese->English)

- [ ] **Step 1: Modify `translate_news()` to preserve English originals**

Update the return value to include `title_en` and `content_en` from originals:

```python
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
```

- [ ] **Step 2: Add `_translate_zh_to_en()` for plain text**

```python
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
```

- [ ] **Step 3: Add `_translate_html_zh_to_en()` for HTML content**

```python
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
```

- [ ] **Step 4: Add `translate_news_zh_to_en()` method**

```python
def translate_news_zh_to_en(self, news_item: Dict[str, Any]) -> Dict[str, Any]:
    """翻译单条中文新闻为英文，中文原文保留，英文存入 _en 字段"""
    try:
        title = news_item.get('title', '')
        content = news_item.get('content', news_item.get('description', ''))

        title_en = self._translate_zh_to_en(title) if title else ''
        content_en = self._translate_html_zh_to_en(content) if content else ''

        return {
            **news_item,
            'title': title,              # 中文原标题
            'content': content,          # 中文原内容
            'title_en': title_en or title,
            'content_en': content_en or content,
        }
    except Exception as e:
        logger.error(f"Error translating news (zh->en): {e}")
        return news_item
```

- [ ] **Step 5: Add `translate_batch_zh_to_en()` method**

```python
def translate_batch_zh_to_en(self, news_items: list) -> list:
    """批量翻译中文新闻为英文"""
    translated = []
    for i, item in enumerate(news_items):
        logger.info(f"Translating zh->en {i+1}/{len(news_items)}: {item.get('title', '')[:50]}...")
        translated_item = self.translate_news_zh_to_en(item)
        translated.append(translated_item)
    return translated
```

- [ ] **Step 6: Verify manually**

In a Python REPL (with API key set):

```bash
python3 -c "
import yaml, os
from dotenv import load_dotenv
load_dotenv()
with open('config.yaml') as f:
    config = yaml.safe_load(f.read().replace('\${ANTHROPIC_API_KEY}', os.environ.get('ANTHROPIC_API_KEY', '')))
from translator import Translator
t = Translator(config)
result = t.translate_news_zh_to_en({'title': '测试标题', 'content': '<p>这是一段测试内容。</p>'})
print('ZH title:', result.get('title'))
print('EN title:', result.get('title_en'))
print('EN content:', result.get('content_en'))
"
```

Expected: `title` stays Chinese, `title_en` is English.

- [ ] **Step 7: Commit**

```bash
git add translator.py
git commit -m "feat: 翻译模块支持双语字段和中文->英文翻译"
```

---

### Task 2: saver.py — save `_en.html` alongside primary file

**File:** `saver.py`

When a news item has `title_en` + `content_en`, save a second `_en.html` file.

- [ ] **Step 1: Modify `save_news()` to write bilingual files**

Update `save_news()` to detect and save the English version:

```python
def save_news(self, news_item: Dict[str, Any], source: str, date: str = None) -> str:
    """保存单条新闻为 HTML 文件，如有双语字段则同时保存英文版"""
    if date is None:
        date = news_item.get('published', datetime.now().strftime(self.date_format))

    dir_path = os.path.join(self.output_dir, source, date)
    os.makedirs(dir_path, exist_ok=True)

    title = news_item.get('title', '')
    filename = self._generate_filename(title)
    file_path = os.path.join(dir_path, f"{filename}.html")

    html_content = self._generate_html(news_item, source, date)
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
```

- [ ] **Step 2: Verify manually**

```bash
python3 -c "
from saver import HTMLSaver
import os
s = HTMLSaver({'OUTPUT_DIR': '/tmp/test_news'})
s.save_news({
    'title': '测试标题', 'content': '<p>中文内容</p>',
    'title_en': 'Test Title', 'content_en': '<p>English content</p>',
    'published': '2026-03-11', 'link': ''
}, 'idaily', '2026-03-11')
print(os.listdir('/tmp/test_news/idaily/2026-03-11/'))
"
```

Expected: Two files — one Chinese-named and one with `_en` suffix.

- [ ] **Step 3: Commit**

```bash
git add saver.py
git commit -m "feat: 保存器支持同时保存英文版 _en.html"
```

---

## Chunk 2: Backend — main.py + webapp.py

### Task 3: main.py — enable iDaily translation

**File:** `main.py`

- [ ] **Step 1: Add `translate_to_en` parameter to `process_source()`**

Update the function signature and body:

```python
def process_source(
    fetcher: RSSFetcher,
    translator: Translator,
    saver: HTMLSaver,
    url: str,
    source: str,
    source_type: str,
    date: str = None,
    need_translate: bool = True,
    translate_to_en: bool = False,  # 新增：中文->英文（iDaily）
) -> int:
    """处理单个新闻源"""
    logger = logging.getLogger(__name__)

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

    today_news = fetcher.get_today_news(news_items, target_date=date)
    if not today_news:
        logger.warning(f"No recent news found for {source}")
        return 0

    actual_date = today_news[0].get('published', date)
    logger.info(f"Processing {len(today_news)} news items for {actual_date}")

    if translator is not None and need_translate:
        # Kagi: 英文->中文，归档英文原文
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

    saved_files = saver.save_batch(translated_news, source, actual_date)
    return len(saved_files)
```

- [ ] **Step 2: Update iDaily call in `main()` to use `translate_to_en=True`**

```python
# 处理 iDaily 新闻源（中文，翻译为英文生成双语）
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
```

- [ ] **Step 3: Verify dry run**

```bash
python3 main.py --source idaily --no-translate --date 2026-03-11 --verbose
ls news/idaily/
```

Expected: No crashes, idaily files created (no English translation since `--no-translate`).

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: main.py 支持 iDaily 中文->英文翻译，生成双语文件"
```

---

### Task 4: webapp.py — load bilingual files, return extended JSON

**File:** `webapp.py`

- [ ] **Step 1: Add `_find_en_file()` helper**

Add this function before `_get_news_for_date()`:

```python
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
```

- [ ] **Step 2: Update `_get_news_for_date()` to load bilingual pairs**

Replace the existing function:

```python
def _get_news_for_date(date: str) -> dict:
    """获取指定日期的所有新闻，包含双语字段。"""
    result = {"date": date, "science": [], "tech": [], "idaily": []}

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
```

- [ ] **Step 3: Verify API response**

```bash
python3 webapp.py &
sleep 1
curl -s http://localhost:3010/api/news/2026-03-09 | python3 -m json.tool | grep -E '"title|content_en|title_en"' | head -20
kill %1
```

Expected: `title_en` and `content_en` fields appear for articles with paired `_en.html` files.

- [ ] **Step 4: Commit**

```bash
git add webapp.py
git commit -m "feat: webapp 加载双语文件，API 返回 title_en/content_en 字段"
```

---

## Chunk 3: Frontend — news.html

### Task 5: Tab switcher + TTS in news.html

**File:** `templates/news.html`

- [ ] **Step 1: Add CSS for tab switcher and TTS button**

In the `<style>` block, add after `.news-card .meta a` rule:

```css
/* 语言 Tab 切换器 */
.lang-tabs {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 10px;
}
.lang-tab {
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 12px;
    border: 1px solid #d0d7de;
    background: none;
    cursor: pointer;
    color: #555;
    -webkit-appearance: none;
    -webkit-tap-highlight-color: rgba(102,126,234,0.1);
    transition: background 0.15s, color 0.15s;
}
.lang-tab.active {
    background: #667eea;
    border-color: #667eea;
    color: white;
}
.tts-btn {
    margin-left: auto;
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 12px;
    border: 1px solid #d0d7de;
    background: none;
    cursor: pointer;
    color: #555;
    -webkit-appearance: none;
    -webkit-tap-highlight-color: rgba(102,126,234,0.1);
}
.tts-btn.playing {
    border-color: #e74c3c;
    color: #e74c3c;
}
```

- [ ] **Step 2: Add TTS state management before `init()` in the script**

```javascript
// TTS 播放状态
const ttsSupported = 'speechSynthesis' in window;
let ttsQueue = [];       // 当天所有文章的队列条目
let ttsCurrentIdx = -1;  // 当前播放的队列索引
let ttsPlaying = false;
let ttsCurrentBtn = null;

function ttsStop() {
    window.speechSynthesis.cancel();
    ttsPlaying = false;
    if (ttsCurrentBtn) {
        ttsCurrentBtn.textContent = '▶';
        ttsCurrentBtn.classList.remove('playing');
        ttsCurrentBtn = null;
    }
    ttsCurrentIdx = -1;
}

function ttsGetPlainText(html) {
    const tmp = document.createElement('div');
    safeSetHTML(tmp, html);
    return tmp.textContent || tmp.innerText || '';
}

function ttsPlayAt(idx) {
    if (idx >= ttsQueue.length) {
        // 播放完毕
        ttsPlaying = false;
        if (ttsCurrentBtn) {
            ttsCurrentBtn.textContent = '▶';
            ttsCurrentBtn.classList.remove('playing');
            ttsCurrentBtn = null;
        }
        return;
    }

    const { article, getLang, btn } = ttsQueue[idx];

    // 重置上一个按钮
    if (ttsCurrentBtn && ttsCurrentBtn !== btn) {
        ttsCurrentBtn.textContent = '▶';
        ttsCurrentBtn.classList.remove('playing');
    }

    ttsCurrentIdx = idx;
    ttsCurrentBtn = btn;
    btn.textContent = '⏸';
    btn.classList.add('playing');
    ttsPlaying = true;

    const lang = getLang();
    const title = lang === 'en' ? (article.title_en || article.title) : article.title;
    const content = lang === 'en' ? (article.content_en || article.content) : article.content;
    const text = title + '. ' + ttsGetPlainText(content);

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang === 'en' ? 'en-US' : 'zh-CN';
    utter.onend = () => ttsPlayAt(idx + 1);
    utter.onerror = () => {
        ttsPlaying = false;
        btn.textContent = '▶';
        btn.classList.remove('playing');
    };
    window.speechSynthesis.speak(utter);
}
```

- [ ] **Step 3: Reset queue in `renderDay()` and rebuild `renderCategory()`**

At the very start of `renderDay()`, reset the TTS queue:

```javascript
function renderDay(data) {
    ttsQueue = [];   // 重置队列
    // ... existing code below
```

Replace the entire `for (const article of articles)` loop in `renderCategory()` with:

```javascript
for (let i = 0; i < articles.length; i++) {
    const article = articles[i];
    const card = document.createElement('div');
    card.className = 'news-card';
    const hasBilingual = !!(article.title_en && article.content_en);

    // 当前显示语言（默认英文，无英文则中文）
    let currentLang = hasBilingual ? 'en' : 'zh';

    // 语言 Tab 行
    const langTabs = document.createElement('div');
    langTabs.className = 'lang-tabs';

    const enBtn = document.createElement('button');
    enBtn.className = 'lang-tab' + (currentLang === 'en' ? ' active' : '');
    enBtn.textContent = 'EN';
    if (!hasBilingual) enBtn.style.display = 'none';

    const zhBtn = document.createElement('button');
    zhBtn.className = 'lang-tab' + (currentLang === 'zh' ? ' active' : '');
    zhBtn.textContent = '中文';

    const ttsBtn = document.createElement('button');
    ttsBtn.className = 'tts-btn';
    ttsBtn.textContent = '▶';
    if (!ttsSupported) ttsBtn.style.display = 'none';

    langTabs.appendChild(enBtn);
    langTabs.appendChild(zhBtn);
    langTabs.appendChild(ttsBtn);
    card.appendChild(langTabs);

    // 标题
    const titleEl = document.createElement('h3');
    function updateTitle() {
        titleEl.textContent = currentLang === 'en'
            ? (article.title_en || article.title)
            : article.title;
    }
    updateTitle();
    card.appendChild(titleEl);

    // 内容
    const summaryEl = document.createElement('div');
    summaryEl.className = 'summary';

    function updateContent() {
        const html = currentLang === 'en'
            ? (article.content_en || article.content)
            : article.content;
        if (html.length > 300) summaryEl.classList.add('collapsed');
        else summaryEl.classList.remove('collapsed');
        safeSetHTML(summaryEl, html);
    }
    updateContent();
    card.appendChild(summaryEl);

    // 展开/收起
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'toggle-btn';
    function updateToggle() {
        const html = currentLang === 'en'
            ? (article.content_en || article.content)
            : article.content;
        if (html.length > 300) {
            toggleBtn.style.display = 'block';
            toggleBtn.textContent = summaryEl.classList.contains('collapsed') ? '展开全文' : '收起';
        } else {
            toggleBtn.style.display = 'none';
        }
    }
    updateToggle();
    toggleBtn.addEventListener('click', () => {
        summaryEl.classList.toggle('collapsed');
        toggleBtn.textContent = summaryEl.classList.contains('collapsed') ? '展开全文' : '收起';
    });
    card.appendChild(toggleBtn);

    // 原文链接
    if (article.link) {
        const meta = document.createElement('div');
        meta.className = 'meta';
        const link = document.createElement('a');
        link.href = article.link;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = '查看原文 →';
        meta.appendChild(link);
        card.appendChild(meta);
    }

    // Tab 切换事件
    enBtn.addEventListener('click', () => {
        currentLang = 'en';
        enBtn.classList.add('active'); zhBtn.classList.remove('active');
        updateTitle(); updateContent(); updateToggle();
    });
    zhBtn.addEventListener('click', () => {
        currentLang = 'zh';
        zhBtn.classList.add('active'); enBtn.classList.remove('active');
        updateTitle(); updateContent(); updateToggle();
    });

    // TTS 注册到队列
    const queueIdx = ttsQueue.length;
    ttsQueue.push({ article, getLang: () => currentLang, btn: ttsBtn });

    ttsBtn.addEventListener('click', () => {
        if (ttsPlaying && ttsCurrentIdx === queueIdx) {
            // 暂停
            window.speechSynthesis.pause();
            ttsPlaying = false;
            ttsBtn.textContent = '▶';
            ttsBtn.classList.remove('playing');
        } else if (!ttsPlaying && ttsCurrentIdx === queueIdx && window.speechSynthesis.paused) {
            // 继续
            window.speechSynthesis.resume();
            ttsPlaying = true;
            ttsBtn.textContent = '⏸';
            ttsBtn.classList.add('playing');
        } else {
            // 从当前条目开始播放
            ttsStop();
            ttsPlayAt(queueIdx);
        }
    });

    parent.appendChild(card);
}
```

- [ ] **Step 4: Verify in browser**

```bash
python3 webapp.py
```

Open `http://localhost:3010/news` and verify:
- [ ] EN / 中文 tabs appear on all cards
- [ ] For articles without `title_en`, only 中文 tab is visible
- [ ] Default tab is EN for bilingual articles
- [ ] Switching tabs updates title and content
- [ ] ▶ button appears; click to start TTS
- [ ] Button changes to ⏸ while playing
- [ ] Click ⏸ to pause; click ▶ to resume
- [ ] Article finishes -> next article auto-plays
- [ ] Safari on iPhone: all interactions work

- [ ] **Step 5: Commit**

```bash
git add templates/news.html
git commit -m "feat: 新闻卡片支持双语 Tab 切换和 TTS 播放控制"
```

---

## Final Verification

- [ ] Run `python3 main.py --source idaily --verbose` -> confirm `_en.html` files generated
- [ ] Run `python3 main.py --source kagi --verbose` -> confirm `_en.html` files generated  
- [ ] Open in Safari on iPhone -> confirm tabs and TTS work

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat(2026-03-11-01): 双语新闻展示与 TTS 播放完整实现

- 翻译模块保留英文原文，新增中文->英文翻译方法
- 保存器自动生成 _en.html 双语文件
- main.py 支持 iDaily 中文->英文翻译
- webapp API 返回双语字段 title_en/content_en
- 前端新闻卡片支持 EN/中文 Tab 切换和 TTS 播放控制"
```
