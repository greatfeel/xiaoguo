# 2026-03-09-01
## 构建一个前端网页应用
- 首页：是几个应用的入口，目前可以点击的只有一个应用热点新闻，另外一个入口是“作文宝”，但是不可点击
- 热点新闻，首先读取news目录下面最新的新闻，如果是当天则读取当天，如果没有当天读取最近的一天，有一个Bar显示找到的那一天
- 首先显示科学新闻，有一个bar显示科学，读取news/kagi/science
- 然后显示技术新闻，有一个bar显示技术，读取news/kagi/tech
- 最后显示热点新闻，有一个bar显示热点，读取news/idaily
- 当这一天显示完了，检测下滑到了底部，刷新获取旧一天的新闻以此类推
- 端口是3010

# 2026-03-09-02
## 前端展示的修改 
适合在苹果手机的 Safari 进行浏览 

## 后端抓取的修改
- 抓取kagi新闻的存储日期（即放入对应的文件目录）按照<lastBuildDate>Mon, 09 Mar 2026 12:03:24 +0000</lastBuildDate>，而不是<pubDate>Sun, 08 Mar 2026 23:40:00 +0000</pubDate>

# 2026-03-10-01
## 如果环境变量中没有ANTHROPIC_API_KEY，从.env文件中读取

# 2026-03-10-02
在网站首页构建一个新的入口菜单，高考日历，点击进去将下面的日历（来源 outlook）嵌入在页面中
https://outlook.live.com/owa/calendar/26555a2a-43dc-4283-a125-ed904dea08e1/e0a7b3ff-bb52-4509-a9a2-c84ec7381e5b/cid-FF1DD0E83EAD4EF6/index.html

# 2026-03-10-03
在网站首页构建一个新的入口菜单，我的任务，点击进去将下面的代码嵌入在页面中
<iframe src="https://therapeutic-torta-faf.notion.site/ebd//31f19d94caea80b1a1ede06d82b1b7ac?v=31f19d94caea806bbaef000c73687047" width="100%" height="600" frameborder="0" allowfullscreen />