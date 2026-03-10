# RSS 新闻抓取程序 - 任务计划

## 目标
创建 Python 程序抓取 RSS 新闻，翻译为中文，保存为 HTML 文件

## 信息源
1. **Kagi News**:
   - https://news.kagi.com/science.xml
   - https://news.kagi.com/tech.xml
   - 保存路径: `news/kagi/{日期}/`

2. **iDaily**:
   - https://plink.anyfeeder.com/idaily/today
   - 保存路径: `news/idaily/{日期}/`

## 实现步骤

### Step 1: 项目结构与配置
- [ ] 创建配置文件 `config.yaml` 包含：
  - `ANTHROPIC_MODEL`: 大模型名称
  - `ANTHROPIC_BASE_URL`: API 端点
  - `ANTHROPIC_AUTH_TOKEN`: API 密钥
- [ ] 创建目录结构

### Step 2: RSS 抓取模块
- [ ] 实现 `fetch_rss.py` - 抓取 RSS 源
- [ ] 支持 Kagi RSS (science.xml, tech.xml)
- [ ] 支持 iDaily JSON

### Step 3: 翻译模块
- [ ] 实现 `translator.py` - 调用大模型 API 翻译
- [ ] 翻译标题和正文
- [ ] 保留 HTML 格式

### Step 4: HTML 保存模块
- [ ] 实现 `save_html.py` - 保存为单独 HTML 文件
- [ ] 按日期创建目录

### Step 5: 主程序
- [ ] 实现 `main.py` - 整合所有模块
- [ ] 支持命令行参数

### Step 6: 定时任务
- [ ] 创建 cron 任务配置
- [ ] 添加使用说明

## 技术栈
- Python 3.10+
- feedparser (RSS 解析)
- requests (HTTP 请求)
- anthropic SDK (翻译)
- pyyaml (配置文件)