# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RSS news fetcher and translator. Fetches news from Kagi News (science/tech RSS) and iDaily (JSON API), translates to Chinese via LLM API (Anthropic-compatible), and saves as styled HTML files. Written in Python 3.

## Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run (fetch + translate all sources)
python3 main.py

# Fetch without translation
python3 main.py --no-translate

# Single source
python3 main.py --source kagi
python3 main.py --source idaily

# Specific date
python3 main.py --date 2026-03-08

# Verbose logging
python3 main.py --verbose
```

No test framework is configured. No linter/formatter is configured.

## Architecture

Four modules with clear separation:

- **main.py** — CLI entry point. Loads YAML config (with `${ENV_VAR}` substitution), sets up logging, orchestrates the pipeline.
- **fetcher.py** — `RSSFetcher` class. `fetch_kagi_rss()` parses RSS XML via feedparser; `fetch_idaily()` parses JSON API. `get_today_news()` filters by date.
- **translator.py** — `Translator` class. Uses Anthropic SDK pointed at a configurable base URL. `translate_batch()` and `_translate_html()` preserve HTML structure during translation.
- **saver.py** — `HTMLSaver` class. Generates standalone styled HTML pages. Handles filename sanitization and date-based directory structure.

**Data flow**: Fetch RSS/JSON → Filter by date → Translate via LLM → Generate HTML → Save to `news/<source>/<category>/<date>/`

## Configuration

`config.yaml` holds API settings (model, base URL, auth token), source URLs, output directory, and HTTP timeouts. Auth token supports `${ANTHROPIC_API_KEY}` environment variable substitution.

## Code Conventions

- Google-style docstrings, comments in Chinese
- Full type hints (`typing` module)
- Snake_case functions, PascalCase classes
- Each module uses `logging.getLogger(__name__)`

## Plan Rules
- When you are asked to work on a requirement with a numbering format like # 2026-03-07-01, please read the corresponding section from `docs/plans/my_plan.md` and do not involve content from other sections.

## Some Preference Notes
- We prefer Log.info over System.out.println

## Language Notes
- Please use Simplified Chinese and English to communicate, write, and output.
- Japanese and Korea are forbidden to use.

## GitHub Instructions
- When committing, if the fix addresses a previously submitted issue, add a comment to the issue explaining the fix details.
- When committing the modifications accoring to the specific section in my_plan.md, includes the description in that section in the commit message.
