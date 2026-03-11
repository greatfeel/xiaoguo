# Bilingual News Display + TTS Design
Date: 2026-03-11
Plan Reference: 2026-03-11-01

## Overview

Add bilingual (English/Chinese) tab display for all news articles and TTS playback for each article.

## Requirements

1. Keep Kagi English news, show each item with two tabs (English default, switch to Chinese)
2. For iDaily Chinese news, translate to English via LLM (same backend flow as Kagi)
3. Add TTS button per article to play/pause; auto-continue to next article
4. TTS reads the currently visible tab's language

## Decisions Made

- Translation: Backend (Approach A) — mirrors Kagi workflow, saves `title.html` + `title_en.html`
- TTS: Web Speech API (browser built-in, no API key, works on Safari iOS)
- TTS language: Reads active tab's content (English or Chinese)
- Continuation: Auto-advance to next article when current finishes

## Backend Design

### main.py

- Modify `process_source()` for iDaily: enable translation (`need_translate=True`)
- Save both Chinese (original) and English (translated) versions to `news/idaily/<date>/`

### saver.py

- Extend `save_batch()` to write bilingual articles:
  - `title.html` — Chinese version
  - `title_en.html` — English version
- For Kagi: save archive (original English as `title_en.html`) + translation (Chinese as `title.html`)

### Article data structure

```python
{
  'title': '中文标题',
  'title_en': 'English Title',
  'content': '<p>中文内容</p>',
  'content_en': '<p>English content</p>',
  'link': 'http://...',
  'source': 'iDaily',
  'published': '2026-03-11'
}
```

## Frontend Design

### webapp.py

- `_get_news_for_date()`: load paired `*_en.html` files alongside Chinese versions
- Include `title_en` and `content_en` in the JSON response per article
- For Kagi: read English originals from `archives/` directory

### news.html — Card UI

```
┌─────────────────────────────────┐
│ Title      [▶ Play] [EN] [中文] │
│─────────────────────────────────│
│ Content in active tab language  │
│                          原文→  │
└─────────────────────────────────┘
```

- Tab buttons `EN` / `中文` switch title + content
- Active tab is visually highlighted
- Default active tab: English

### TTS Behavior

- Click `▶` → `window.speechSynthesis.speak()` with active language text
- Button shows `⏸` while playing; click to pause
- Click `▶` after pause → resume from current position
- On article end → auto-start next article's TTS (same category, sequential order)
- Only one article plays at a time (stops previous if clicking new one)

## Error Handling

- `speechSynthesis` not supported → hide TTS button
- Language not available → fallback to default voice
- Speech fails mid-playback → reset button to `▶`
- iDaily translation fails → save Chinese only, frontend hides EN tab if `content_en` absent
- `content_en` missing from API → show single-language view, no tab switcher

## File Changes Summary

| File | Change |
|------|--------|
| `main.py` | Enable iDaily translation |
| `saver.py` | Save `_en.html` for Kagi archives + iDaily bilingual |
| `translator.py` | Return `title_en` + `content_en` fields |
| `webapp.py` | Load paired bilingual files, return extended JSON |
| `templates/news.html` | Tab switcher UI, TTS button, playback state |
