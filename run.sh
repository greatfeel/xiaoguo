#!/bin/bash
cd /Users/edy/greatfeel/dev/projects/xiaoguome
.venv/bin/python main.py --config config.yaml >> logs/news_fetcher.log 2>&1
