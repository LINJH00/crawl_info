# AI 新闻 & 论文多源爬取脚本合集

本仓库汇集了多个轻量级 Python 爬虫，可批量抓取人工智能相关 **新闻 / 博客 / 论文**，统一输出为 JSONL。脚本全部依赖 `requests + BeautifulSoup`，如遇复杂反爬自动切换 `cloudscraper` 或 `Playwright`。

---
## 目录结构

```text
.
├── AI_Weekly/                         # AI Weekly Newsletter 最新一期外链爬取
│   ├── crawl_aiweekly_api.py
│   └── data/
├── TechCrunch_AI/                     # TechCrunch AI 分类
│   ├── crawl_tec_api.py
│   └── data/
├── Huggingface_Blog/                  # HF 官方 Blog
│   ├── crawl_hfb_api.py
│   └── data/
├── Huggingface_trending_paper/        # HF Trending Papers
│   ├── crawl_hf_paper_api.py
│   └── data/
├── Synced_Review/                     # 机器之心英文站 Synced
│   ├── crawl_sync_api.py
│   └── data/
├── 机器之心/                           # 中文机器之心
│   ├── crawl_jqzx_api.py
│   └── data/
├── 新智源/                             # BAAI 新智源公众号
│   ├── crawl_xzy_api.py
│   └── data/
├── 量子位/                             # 量子位官网
│   ├── crawl_lzw_api.py
│   └── data/
├── requirements.txt                   # 统一依赖
└── README.md
```

---
## 快速开始

1. **克隆 & 创建虚拟环境（可选）**
   ```bash
   git clone <repo_url>
   cd get_info_form_web  # 请根据实际路径调整

   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```
2. **安装依赖**
   ```bash
   pip install -r requirements.txt        # 基础依赖
   playwright install chromium            # 若需 Playwright fallback
   ```

---
## 统一输出格式
每条记录一行 JSON：
```json
{"url": "文章链接", "title": "文章标题", "date": "发布日期", "content": "正文文本或图片 URL"}
```
脚本默认写入各自 `data/` 子目录，可用 `--out` 自定义路径。

---
## 运行示例
| 目标 | 命令示例 | 说明 |
|------|----------|------|
| AI Weekly 最新 30 条 | `python AI_Weekly/crawl_aiweekly_api.py --limit 30 --out data/aiweekly.jsonl` | 自动展开短链并跳过 Sponsor |
| TechCrunch AI 20 篇 | `python TechCrunch_AI/crawl_tec_api.py --limit 20` | 不带 `--out` 默认写入 `data/techcrunch_ai.jsonl` |
| HuggingFace Blog 全站最近 50 篇 | `python Huggingface_Blog/crawl_hfb_api.py --limit 50` | |

通用参数：
- `--limit` ：抓取数量，脚本自带默认值。
- `--out`   ：输出文件。

---
## 反爬与调试
- `fetch_html()` 内置 **三级回退**：`requests → cloudscraper → Playwright-Chromium`。
- 每次请求随机 `User-Agent`，自带节流 `time.sleep(random.uniform(1,2))`。
- `AI_Weekly` 脚本可取消注释生成 `debug/debug_home.html`、`debug/debug_issue.html` 追踪页面结构变更。

### 代理池（可选）
在 `fetch_html()` 中加入 `proxies={"http": "http://<ip>:<port>", ...}` 即可接入住宅/ISP 代理，显著降低 403 / CAPTCHA 触发率。

---
## 常见问题
1. **Playwright 报未安装浏览器**  
   运行 `playwright install chromium`（或 `firefox`）。
2. **Cloudflare 仍阻断**  
   使用住宅代理或降低抓取频率；必要时手动通过验证导出 cookie。
3. **输出数量少于 `--limit`**  
   日志 `[warn] skip ...` 表示重试 3 次仍失败，可提高超时或次数。

---
## 法律声明
本仓库脚本仅供学习与科研使用。请遵守各站点版权及 robots 协议，商业/大规模抓取前务必征得原站点书面许可。

---
Happy Crawling
