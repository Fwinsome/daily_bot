import os
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime
import feedparser

# 配置 Server酱
TOKEN = os.environ.get("SERVERCHAN_TOKEN", "491:lEN-K3hGEthDUM1z-Lue78zuYHWUsXk6hm")
CHAT_ID = 18148

# 配置 Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 配置 AI RSS 源
AI_RSS = "https://raw.githubusercontent.com/imjuya/juya-ai-daily/master/rss.xml"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_rss(url, limit=10):
    if not url:
        return []
    try:
        d = feedparser.parse(url)
        entries = []
        for entry in d.entries[:limit]:
            entries.append(f"标题: {entry.get('title', '')}\n摘要: {entry.get('summary', '')}")
        return entries
    except Exception as e:
        print(f"Failed to fetch RSS from {url}: {e}")
        return []

def fetch_github_commits(repo="ZhuLinsen/daily_stock_analysis", limit=10):
    try:
        url = f"https://api.github.com/repos/{repo}/commits"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, context=ctx)
        data = json.loads(response.read().decode('utf-8'))
        
        commits = []
        for c in data[:limit]:
            msg = c.get('commit', {}).get('message', '').split('\n')[0]
            commits.append(f"- {msg}")
        return commits
    except Exception as e:
        print(f"Failed to fetch commits for {repo}: {e}")
        return []

def main():
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not set. Exiting.")
        return

    print("Fetching AI news...")
    ai_news = fetch_rss(AI_RSS, limit=5)
    
    print("Fetching Economy/Finance (daily_stock_analysis) news...")
    economy_news = fetch_github_commits()
    if not economy_news:
        economy_news = ["暂无更新。"]

    prompt = f"""
请分析以下今天来自两个领域（AI、财经/量化开源项目）的信息。
任务要求：
1. 找出这两个领域共同提到的核心事件或关联（例如 AI 技术在财经领域的应用、自动化分析等），将其在最开头高亮显示，并用一句话说明这件事情的跨领域影响。如果没有共同事件，也请在一开头高亮说明“今日各领域无共同重大事件”。
2. 分别用简短的话总结这两个领域最值得关注的内容。对于财经领域，内容来自于股票智能分析系统的最新代码更新日志。

以下是原始数据：

【AI领域新闻】
{chr(10).join(ai_news)}

【财经量化系统更新 (ZhuLinsen/daily_stock_analysis)】
{chr(10).join(economy_news)}
"""

    print("Generating summary with Gemini...")
    try:
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        req_data = json.dumps(payload).encode('utf-8')
        gemini_req = urllib.request.Request(gemini_url, data=req_data, headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(gemini_req, context=ctx)
        resp_data = json.loads(response.read().decode('utf-8'))
        summary = resp_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "未能生成摘要")
    except Exception as e:
        print(f"Failed to generate content with Gemini: {e}")
        try:
            print(e.read().decode('utf-8'))
        except:
            pass
        return

    text_to_send = f"**每日新闻汇总 ({datetime.now().strftime('%Y-%m-%d')})**\n\n{summary}"

    # Send via ServerChan Bot
    bot_url = f'https://bot-go.apijia.cn/bot{TOKEN}/sendMessage'
    payload = {
        "chat_id": CHAT_ID,
        "text": text_to_send,
        "parse_mode": "markdown",
        "silent": False
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(bot_url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        response = urllib.request.urlopen(req, context=ctx)
        result = json.loads(response.read().decode('utf-8'))
        if result.get('ok'):
            print(f"Successfully sent daily news summary.")
        else:
            print(f"Failed to send daily news: {result}")
    except Exception as e:
        print(f"API request failed: {e}")
        try:
            print(e.read().decode('utf-8'))
        except:
            pass

if __name__ == '__main__':
    main()
