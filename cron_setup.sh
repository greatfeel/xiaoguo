# Cron Setup

## 添加定时任务

运行以下命令编辑 crontab:

```bash
crontab -e
```

添加以下行（每日早上 8 点执行）:

```bash
# 每日 8:00 执行新闻抓取
0 8 * * * cd /path/to/xiaoguome && /usr/bin/python3 main.py --config config.yaml >> /path/to/xiaoguome/logs/news_fetcher.log 2>&1
```

或者使用虚拟环境:

```bash
0 8 * * * cd /path/to/xiaoguome && /path/to/venv/bin/python main.py --config config.yaml >> /path/to/xiaoguome/logs/news_fetcher.log 2>&1
```

## 创建日志目录

```bash
mkdir -p /path/to/xiaoguome/logs
```

## 验证

查看当前定时任务:

```bash
crontab -l
```

查看日志:

```bash
tail -f /path/to/xiaoguome/logs/news_fetcher.log
```

## 手动运行

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export ANTHROPIC_API_KEY="your-api-key"

# 运行程序
python main.py --config config.yaml

# 只抓取不翻译
python main.py --config config.yaml --no-translate

# 指定日期
python main.py --config config.yaml --date 2025-03-08

# 只抓取指定源
python main.py --config config.yaml --source kagi
```