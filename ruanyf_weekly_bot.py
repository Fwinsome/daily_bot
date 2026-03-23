import os
import json
import ssl
import re
import urllib.request
from datetime import datetime

# ---------- 配置 ----------
TOKEN = os.environ.get("SERVERCHAN_TOKEN", "")
CHAT_ID = int(os.environ.get("CHAT_ID", "18148"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
STATE_DIR = "state"
STATE_FILE = os.path.join(STATE_DIR, "ruanyf_bot_state.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ---------- 获取周刊列表 ----------
def get_issues():
    url = "https://api.github.com/repos/ruanyf/weekly/contents/docs"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    response = urllib.request.urlopen(req, context=ctx)
    data = json.loads(response.read().decode("utf-8"))

    issues = [
        file["name"]
        for file in data
        if file["name"].startswith("issue-") and file["name"].endswith(".md")
    ]

    def extract_num(name):
        match = re.search(r"issue-(\d+)\.md", name)
        return int(match.group(1)) if match else 0

    issues.sort(key=extract_num)
    return issues

# ---------- 清洗 markdown 内容 ----------
def clean_markdown(content):
    """去掉周刊原始 markdown 中的头图、HTML 注释等噪音"""
    # 去掉图片语法（保留链接）
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    # 去掉 HTML 注释
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # 去掉多余空行
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()

# ---------- Gemini 摘要 ----------
def summarize_weekly(issue_name, content):
    if not GEMINI_API_KEY:
        # 没有 Gemini 时 fallback 到截断原文
        return None

    prompt = f"""你是一个专业、简洁的技术 newsletter 编辑。
请从下面这篇阮一峰周刊（{issue_name}）中提炼出最值得读者关注的内容。

提炼规则：
1. 只选本期最有价值的 4~6 个话题/文章。
2. 对每个话题，用一句话说明它讲了什么（不超过 40 字）。
3. 如果话题有链接，附上链接；如果没有，注明"无原文链接"。
4. 不要提及周刊名称或期号，不要写前言/结语，直接输出结构化内容。
5. 每个话题前加 "📌" 前缀。

格式示例：
📌 话题一句话描述
   链接：xxx（或"无原文链接"）

---

以下是周刊正文：

{content[:8000]}"""  # 限制输入 token，防止超限

    try:
        url = ("https://generativelanguage.googleapis.com/v1beta/models"
               "/gemini-2.0-flash:generateContent"
               f"?key={GEMINI_API_KEY}")
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
              headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=60)
        resp_data = json.loads(resp.read().decode("utf-8"))
        return resp_data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[WARN] Gemini 摘要失败: {e}，fallback 到原文发送")
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
            print(f"[OK] 发送成功")
            return True
        else:
            print(f"[ERROR] 发送失败: {result}")
            return False
    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        return False

def split_long_message(text, max_chars=1800):
    """超长内容拆成多条"""
    if len(text) <= max_chars:
        send_message(text)
        return
    parts = []
    lines = text.split("\n")
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 <= max_chars:
            current += ("\n" if current else "") + line
        else:
            if current:
                parts.append(current)
            current = line
    if current:
        parts.append(current)
    for i, part in enumerate(parts):
        print(f"  -> 第 {i+1}/{len(parts)} 条（{len(part)} 字）")
        send_message(part, silent=(i > 0))

# ---------- 主流程 ----------
def main():
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR)

    try:
        issues = get_issues()
    except Exception as e:
        print(f"[ERROR] 获取周刊列表失败: {e}")
        return

    if not issues:
        print("未找到任何周刊。")
        return

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            current_index = state.get("current_index", max(0, len(issues) - 50))
    else:
        current_index = max(0, len(issues) - 50)

    if current_index >= len(issues):
        print("全部已推送，无新内容。")
        return

    target_issue = issues[current_index]
    print(f"==> 处理 {target_issue} ...")

    raw_url = f"https://raw.githubusercontent.com/ruanyf/weekly/master/docs/{target_issue}"
    req = urllib.request.Request(raw_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        response = urllib.request.urlopen(req, context=ctx)
        content = response.read().decode("utf-8")
    except Exception as e:
        print(f"[ERROR] 抓取内容失败: {e}")
        return

    content = clean_markdown(content)
    github_url = f"https://github.com/ruanyf/weekly/blob/master/docs/{target_issue}"

    # 尝试 Gemini 摘要
    summary = summarize_weekly(target_issue, content)

    date_str = datetime.now().strftime("%Y-%m-%d")

    if summary:
        # 发送摘要版
        header = f"**📮 阮一峰周刊 {target_issue}**\n📅 {date_str}\n\n"
        footer = f"\n\n[📖 阅读原文]({github_url})"
        text = header + summary + footer
        split_long_message(text)
    else:
        # Fallback：截断原文发送
        if len(content) > 19000:
            content = content[:18900] + "\n\n...（内容过长已截断，请点击原文链接阅读全文）"
        text = (
            f"**{target_issue}**\n"
            f"[阅读原文]({github_url})\n\n"
            f"{content}"
        )
        send_message(text)

    # 更新状态
    with open(STATE_FILE, "w") as f:
        json.dump({"current_index": current_index + 1}, f)
    print(f"==> {target_issue} 处理完毕，索引更新为 {current_index + 1}")

if __name__ == "__main__":
    main()
