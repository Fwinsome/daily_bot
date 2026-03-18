import os
import json
import ssl
import re
import urllib.request

TOKEN = os.environ.get("SERVERCHAN_TOKEN", "491:lEN-K3hGEthDUM1z-Lue78zuYHWUsXk6hm")
CHAT_ID = 18148
STATE_DIR = "state"
STATE_FILE = os.path.join(STATE_DIR, "ruanyf_bot_state.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def get_issues():
    url = 'https://api.github.com/repos/ruanyf/weekly/contents/docs'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, context=ctx)
    data = json.loads(response.read().decode('utf-8'))
    
    issues = [file['name'] for file in data if file['name'].startswith('issue-') and file['name'].endswith('.md')]
    def extract_num(name):
        match = re.search(r'issue-(\d+)\.md', name)
        return int(match.group(1)) if match else 0
    
    issues.sort(key=extract_num)
    return issues

def main():
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR)

    try:
        issues = get_issues()
    except Exception as e:
        print(f"Failed to fetch issues: {e}")
        return

    if not issues:
        print("No issues found.")
        return

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            current_index = state.get('current_index', max(0, len(issues) - 50))
    else:
        current_index = max(0, len(issues) - 50)

    if current_index >= len(issues):
        print("All caught up. No new issues to send.")
        return

    target_issue = issues[current_index]
    print(f"Sending {target_issue}...")
    
    raw_url = f'https://raw.githubusercontent.com/ruanyf/weekly/master/docs/{target_issue}'
    req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        response = urllib.request.urlopen(req, context=ctx)
        content = response.read().decode('utf-8')
    except Exception as e:
        print(f"Failed to fetch content for {target_issue}: {e}")
        return
        
    github_url = f"https://github.com/ruanyf/weekly/blob/master/docs/{target_issue}"
    text_to_send = f"**{target_issue}**\n[阅读原文]({github_url})\n\n{content}"
    
    if len(text_to_send) > 20000:
        text_to_send = text_to_send[:19900] + "\n\n...(内容过长，已被截断，请点击原文链接阅读全文)..."

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
            print(f"Successfully sent {target_issue}.")
            with open(STATE_FILE, 'w') as f:
                json.dump({'current_index': current_index + 1}, f)
        else:
            print(f"Failed to send: {result}")
    except Exception as e:
        print(f"API request failed: {e}")
        try:
            print(e.read().decode('utf-8'))
        except:
            pass

if __name__ == '__main__':
    main()
