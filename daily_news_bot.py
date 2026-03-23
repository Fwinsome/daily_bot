import os
import json
import re
import ssl
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser

# ---------- 配置 ----------
TOKEN = os.environ.get("SERVERCHAN_TOKEN", "")
CHAT_ID = int(os.environ.get("CHAT_ID", "18148"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ---------- 数据源配置 ----------
AI_RSS_SOURCES = [
    {"name": "Hacker News",      "url": "https://news.ycombinator.com/rss",              "limit": 10},
    {"name": "VentureBeat AI",   "url": "https://venturebeat.com/category/ai/feed/",            "limit": 5},
    {"name": "TechCrunch AI",   "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "limit": 5},
    {"name": "MIT Tech Review",  "url": "https://www.technologyreview.com/feed/",                "limit": 5},
    {"name": "Bleeding Balls HN","url": "https://hnrss.org/frontpage",                           "limit": 8},
    {"name": "Juya AI Daily",    "url": "https://raw.githubusercontent.com/imjuya/juya-ai-daily/master/rss.xml", "limit": 5},
]

FINANCE_RSS_SOURCES = [
    {"name": "华尔街见闻",       "url": "https://wallstreetcn.com/rss",                   "limit": 8},
    {"name": "36氪",             "url": "https://36kr.com/feed",                          "limit": 8},
    {"name": "FT中文网",         "url": "https://www.ftchinese.com/rss",                  "limit": 5},
    {"name": "新浪财经",         "url": "https://rss.sina.com.cn/news/china/focus15.xml", "limit": 5},
    {"name": "证券时报",         "url": "https://www.stcn.com/rss/",                      "limit": 5},
]

# ---------- 工具函数 ----------
def clean_html(html_text):
    """去掉 HTML 标签和多余空白"""
    if not html_text:
        return ""
    # 去掉 HTML 标签
    text = re.sub(r'<[^>]+>', '', html_text)
    # 解码常见 HTML 实体
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    # 合并多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fetch_rss(sources, limit_per_source=5):
    """抓取多个 RSS 源，按时间去重合并"""
    seen_urls = set()
    all_entries = []

    for src in sources:
        url = src["url"]
        try:
            d = feedparser.parse(url)
            for entry in d.entries[:src.get("limit", limit_per_source)]:
                # 优先用 link 去重
                link = entry.get("link", "").strip()
                if link and link in seen_urls:
                    continue
                seen_urls.add(link)

                title = clean_html(entry.get("title", ""))
                # 优先取 summary-detail（完整摘要），fallback 到 summary（可能是 HTML）
                summary_raw = entry.get("summary_detail", {}).get("value", "") \
                           or entry.get("summary", "") \
                           or entry.get("description", "")
                summary = clean_html(summary_raw)

                # 有些 RSS 的 title 本身就很长，做一次截断
                if len(summary) > 500:
                    summary = summary[:500] + "…"

                all_entries.append({
                    "source": src["name"],
                    "title":  title,
                    "summary": summary,
                    "link":   link,
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"[WARN] 抓取 RSS 失败 {url}: {e}")

    # 按 published 时间逆序（越新越前），没有时间戳的放最后
    # 注意：parsedate_to_datetime 可能返回 aware 或 naive，统一转成 naive 再比较
    def to_naive(dt):
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt

    def sort_key(e):
        try:
            dt = parsedate_to_datetime(e["published"])
            return to_naive(dt)
        except Exception:
            return datetime.min
    all_entries.sort(key=sort_key, reverse=True)
    return all_entries

def dedup_by_title(entries):
    """简单标题去重（防止相似标题重复出现）"""
    if not entries:
        return entries
    result = [entries[0]]
    titles_lower = [entries[0]["title"].lower()]
    for e in entries[1:]:
        title = e["title"].lower()
        # 简单检查：标题是否已存在（包含关系）
        is_dup = any(title in t or t in title for t in titles_lower)
        if not is_dup:
            result.append(e)
            titles_lower.append(title)
    return result

# ---------- Gemini 总结 ----------
def summarize_with_gemini(prompt, model="gemini-3.1-flash-lite-preview"):
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not set.")
        return None
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
               f":generateContent?key={GEMINI_API_KEY}")
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
              headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=60)
        resp_data = json.loads(resp.read().decode("utf-8"))
        candidates = resp_data.get("candidates", [{}])
        content = candidates[0].get("content", {}) if candidates else {}
        parts = content.get("parts", [{}])
        return parts[0].get("text") if parts else None
    except Exception as e:
        print(f"[ERROR] Gemini 调用失败: {e}")
        return None

# ---------- 发送消息 ----------
def send_message(text, silent=False):
    if not TOKEN:
        print("[ERROR] SERVERCHAN_TOKEN 未设置")
        return False
    url = f"https://bot-go.apijia.cn/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "markdown",
        "silent":     silent,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
              headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok"):
            print(f"[OK] 消息发送成功")
            return True
        else:
            print(f"[ERROR] 发送失败: {result}")
            return False
    except Exception as e:
        print(f"[ERROR] 发送请求失败: {e}")
        return False

def split_and_send(text, max_chars=1800):
    """内容过长时拆成多条发送"""
    if len(text) <= max_chars:
        return send_message(text)
    # 按换行分段，尽量保持段落完整
    chunks = []
    lines = text.split("\n")
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 <= max_chars:
            current += ("\n" if current else "") + line
        else:
            if current:
                chunks.append(current)
            current = line
    if current:
        chunks.append(current)
    for i, chunk in enumerate(chunks):
        print(f"  -> 发送第 {i+1}/{len(chunks)} 条...")
        send_message(chunk, silent=(i > 0))  # 第一条有声，后面静音

# ---------- 主流程 ----------
def build_ai_news_prompt(entries):
    """构造 AI 新闻专用的总结 prompt"""
    news_block = "\n".join(
        f"[{i+1}] 来源：{e['source']}\n    标题：{e['title']}\n    摘要：{e['summary']}\n    链接：{e['link']}"
        for i, e in enumerate(entries)
    )
    return f"""你是一个专业、简洁的科技新闻编辑。请从以下今日 AI / 科技领域资讯中提炼出真正有价值的信息。

任务要求：
1. 为每条新闻输出一行「一句话核心要点」（不超过 30 字），紧接着给出原始标题和链接。
2. 按重要性排序（最重要的放最前）。
3. 只保留有价值的内容，无关紧要的新闻可以直接跳过不呈现。
4. 不要重复标题，不要添加你自己的解释性话语，直接输出结构化内容。
5. 标题前加 "🔹" 前缀。

输出格式（严格按此格式）：
🔹 [一句话要点]
   标题：xxx
   链接：xxx

---

以下是原始资讯：

{news_block}"""

def build_finance_news_prompt(entries):
    """构造财经新闻专用的总结 prompt"""
    news_block = "\n".join(
        f"[{i+1}] 来源：{e['source']}\n    标题：{e['title']}\n    摘要：{e['summary']}\n    链接：{e['link']}"
        for i, e in enumerate(entries)
    )
    return f"""你是一个专业、简洁的财经新闻编辑。请从以下今日财经领域资讯中提炼出真正有价值的信息。

任务要求：
1. 为每条新闻输出一行「一句话核心要点」（不超过 30 字），紧接着给出原始标题和链接。
2. 按重要性排序（最重要的放最前）。
3. 只保留有价值的内容，无关紧要的新闻可以直接跳过不呈现。
4. 不要重复标题，不要添加你自己的解释性话语，直接输出结构化内容。
5. 标题前加 "🔸" 前缀。

输出格式（严格按此格式）：
🔸 [一句话要点]
   标题：xxx
   链接：xxx

---

以下是原始资讯：

{news_block}"""

def main():
    if not GEMINI_API_KEY or not TOKEN:
        print("缺少必要的环境变量。")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")

    # ---- 抓取 AI 新闻 ----
    print("==> 抓取 AI / 科技新闻...")
    ai_raw = fetch_rss(AI_RSS_SOURCES)
    ai_raw = dedup_by_title(ai_raw)
    print(f"    共获取 {len(ai_raw)} 条（去重后）")
    if not ai_raw:
        ai_text = "今日暂无 AI 领域资讯。"
    else:
        prompt = build_ai_news_prompt(ai_raw)
        ai_text = summarize_with_gemini(prompt) or "今日 AI 资讯整理失败。"
        print(f"    AI 总结完成，长度 {len(ai_text)} 字")

    # ---- 抓取财经新闻 ----
    print("==> 抓取财经新闻...")
    finance_raw = fetch_rss(FINANCE_RSS_SOURCES)
    finance_raw = dedup_by_title(finance_raw)
    print(f"    共获取 {len(finance_raw)} 条（去重后）")
    if not finance_raw:
        finance_text = "今日暂无财经资讯。"
    else:
        prompt = build_finance_news_prompt(finance_raw)
        finance_text = summarize_with_gemini(prompt) or "今日财经资讯整理失败。"
        print(f"    财经总结完成，长度 {len(finance_text)} 字")

    # ---- 组合发送 ----
    header = f"**📅 每日新闻 {date_str}**\n\n"

    ai_section = f"**【AI · 科技】**\n\n{ai_text}\n\n——\n"
    finance_section = f"**【财经 · 市场】**\n\n{finance_text}"

    # 如果合并后太长，分开发；否则合并为一条
    combined = header + ai_section + finance_section
    if len(combined) > 3500:
        # 分两条发：先发 AI
        send_message(header + ai_section)
        send_message(header + finance_section)
    else:
        split_and_send(combined)

    print("==> 每日新闻发送完成。")

if __name__ == "__main__":
    main()
