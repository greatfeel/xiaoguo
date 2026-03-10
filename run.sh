#!/bin/bash
cd /Users/edy/greatfeel/dev/projects/xiaoguome
source .env 2>/dev/null
.venv/bin/python main.py --config config.yaml >> logs/news_fetcher.log 2>&1
