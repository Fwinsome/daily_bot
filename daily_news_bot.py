import os
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import feedparser
import google.generativeai as genai

# 配置 Server酱
TOKEN = os.environ.get("SERVERCHAN_TOKEN", "491:lEN-K3hGEthDUM1z-Lue78zuYHWUsXk6hm")
CHAT_ID = 18148

# 配置 Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 配置 RSS 源
AI_RSS = "https://raw.githubusercontent.com/imjuya/juya-ai-daily/master/rss.xml"
POLITICS_RSS = os.environ.get("POLITICS_RSS", "")
ECONOMY_RSS = os.environ.get("ECONOMY_RSS", "")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_rss(url, limit=10):
    if not url:
        return []
    try:
        # 使用自定义 requests 或 urllib 可以绕过部分防抓取，这里直接用 feedparser
        d = feedparser.parse(url)
        entries = []
        for entry in d.entries[:limit]:
            entries.append(f"标题: {entry.get('title', '')}\n摘要: {entry.get('summary', '')}")
        return entries
    except Exception as e:
        print(f"Failed to fetch RSS from {url}: {e}")
        return []

def main():
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not set. Exiting.")
        return

    print("Fetching AI news...")
    ai_news = fetch_rss(AI_RSS, limit=5)
    
    print("Fetching Politics news...")
    politics_news = fetch_rss(POLITICS_RSS, limit=10)
    if not politics_news:
        politics_news = ["暂未提供时政 RSS 源或抓取失败。"]
        
    print("Fetching Economy news...")
    economy_news = fetch_rss(ECONOMY_RSS, limit=10)
    if not economy_news:
        economy_news = ["暂未提供政经 RSS 源或抓取失败。"]

    prompt = f"""
请分析以下今天来自三个领域（AI、时政、政经）的新闻。
任务要求：
1. 找出这三个领域共同提到的核心事件，将其在最开头高亮显示，并用一句话说明这件事情在多个领域都有很大的影响。如果没有共同事件，也请在一开头高亮说明“今日各领域无共同重大事件”。
2. 分别用简短的话总结这三个领域最值得关注的内容。

以下是原始新闻数据：

【AI领域新闻】
{chr(10).join(ai_news)}

【时政领域新闻】
{chr(10).join(politics_news)}

【政经领域新闻】
{chr(10).join(economy_news)}
"""

    print("Generating summary with Gemini...")
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        summary = response.text
    except Exception as e:
        print(f"Failed to generate content with Gemini: {e}")
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
