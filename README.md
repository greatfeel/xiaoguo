# RSS 新闻抓取程序

每日自动抓取 RSS 新闻，翻译为中文，保存为 HTML 文件。

## 功能

- 抓取 Kagi News (Science + Tech)
- 抓取 iDaily 新闻
- 翻译为中文（调用大模型 API）
- 保存为独立 HTML 文件

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置

编辑 `config.yaml`：

```yaml
ANTHROPIC_MODEL: "MiniMax-M2.5"
ANTHROPIC_BASE_URL: "https://coding.dashscope.aliyuncs.com/apps/anthropic"
ANTHROPIC_AUTH_TOKEN: "${ANTHROPIC_API_KEY}"
```

设置环境变量：

```bash
export ANTHROPIC_API_KEY="你的API密钥"
```

### 3. 运行

```bash
# 运行全部（抓取+翻译）
python3 main.py

# 不翻译，只保存原文
python3 main.py --no-translate

# 只抓取指定源
python3 main.py --source kagi
python3 main.py --source idaily

# 指定日期
python3 main.py --date 2026-03-08
```

## 定时任务（每日早上 6 点）

### 步骤 1：创建日志目录

```bash
mkdir -p /Users/edy/greatfeel/dev/projects/xiaoguome/logs
```

### 步骤 2：创建运行脚本

创建 `run.sh`：

```bash
#!/bin/bash
cd /Users/edy/greatfeel/dev/projects/xiaoguome
.venv/bin/python main.py --config config.yaml --date 2026-03-08 >> logs/news_fetcher.log 2>&1 
```

添加执行权限：

```bash
chmod +x /Users/edy/greatfeel/dev/projects/xiaoguome/run.sh
```

### 步骤 3：创建 .env 文件（可选）

在项目根目录创建 `.env` 文件：

```
ANTHROPIC_API_KEY=你的API密钥
```

### 步骤 4：添加 cron 任务

```bash
crontab -e
```

添加以下行：

```
0 6 * * * /Users/edy/greatfeel/dev/projects/xiaoguome/run.sh
```

### 验证

查看当前定时任务：

```bash
crontab -l
```

查看运行日志：

```bash
tail -f /Users/edy/greatfeel/dev/projects/xiaoguome/logs/news_fetcher.log
```

## 输出目录

```
news/
├── kagi/
│   ├── science/2026-03-08/
│   │   └── *.html
│   └── tech/2026-03-08/
│       └── *.html
└── idaily/
    └── 2026-03-08/
        └── *.html
```

## 命令行选项

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-c, --config` | 配置文件路径 | config.yaml |
| `-d, --date` | 指定日期 (YYYY-MM-DD) | 今天 |
| `-s, --source` | 新闻源 (kagi/idaily/all) | all |
| `-v, --verbose` | 显示详细日志 | 否 |
| `--no-translate` | 不翻译，直接保存原文 | 否 |