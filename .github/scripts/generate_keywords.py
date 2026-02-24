import os
import json
import glob
import re
import time
import frontmatter
from google import genai

# ========================
# 配置
# ========================
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("請設定環境變數 GEMINI_API_KEY")

client = genai.Client(api_key=api_key)
model_name = "gemini-2.5-flash-lite"

CONTENT_DIR = "content/blog/**/*.md"
CACHE_FILE = "data/keywords_cache.json"   # 存已處理過的 slug
SLEEP_BETWEEN = 10    # 每次 API 呼叫間隔秒數（免費版建議 5）
MAX_RETRY = 3        # 失敗最多重試幾次

# ========================
# 讀取 / 儲存 Cache
# ========================
os.makedirs("data", exist_ok=True)

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
    print(f"📦 載入 cache，已有 {len(cache)} 筆記錄")
else:
    cache = {}
    print("📦 Cache 不存在，從頭開始")

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ========================
# 清理標籤
# ========================
def clean_tags(tags_list):
    cleaned = []
    for tag in tags_list:
        t = re.sub(r'["\'\s]', '', tag.strip()).strip('，。、')
        if t and len(t) <= 15:
            cleaned.append(t)
    return list(set(cleaned))

# ========================
# 呼叫 Gemini（含自動 retry）
# ========================
def get_ai_keywords(content, title):
    prompt = f"""
任務：作為 SEO + 內容專家，為這篇繁體中文部落格文章提取 5 個最核心的語義關鍵字。
嚴格規則：
1. 全部用繁體中文
2. 只用名詞或名詞短語（例如「向量資料庫」「RAG 應用」「Python 自動化」）
3. 不要解釋、不要前言、不要編號、不要多餘文字
4. 輸出格式嚴格為：關鍵字1, 關鍵字2, 關鍵字3, 關鍵字4, 關鍵字5

文章標題：{title}
文章內容（前1500字）：{content[:1500]}
"""

    for attempt in range(1, MAX_RETRY + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt]
            )
            if response.candidates and response.candidates[0].content.parts:
                raw_text = response.candidates[0].content.parts[0].text.strip()
            else:
                raw_text = ""

            tags = re.split(r'[,，、\n]', raw_text)
            cleaned = clean_tags(tags)
            while len(cleaned) < 5:
                cleaned.append("其他")
            return cleaned[:5]

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 60 * attempt  # 第一次等 60 秒，第二次 120 秒
                print(f"  ⚠️ Rate limit！等待 {wait} 秒後重試（第 {attempt}/{MAX_RETRY} 次）...")
                time.sleep(wait)
            else:
                print(f"  ❌ API 錯誤（第 {attempt} 次）：{e}")
                time.sleep(5)

    print("  ❌ 超過重試次數，跳過此篇")
    return []

# ========================
# 主程式
# ========================
files = glob.glob(CONTENT_DIR, recursive=True)
print(f"\n📂 找到 {len(files)} 篇文章\n")

updated_count = 0
skip_count = 0

for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)

        # 跳過草稿
        if post.get('draft') is True:
            continue

        title = post.get('title', '')
        if not title or title.strip() == 'blog':   # ← 加這三行
            print(f"  ⏭️ 跳過（無標題）：{filepath}")
            continue

        # 跳過已有 ai_keywords 的文章（frontmatter 裡有）
        if post.get('ai_keywords'):
            skip_count += 1
            continue

        # 跳過 cache 裡已處理過的（但還沒寫進 md 的備援）
        slug = os.path.splitext(os.path.basename(filepath))[0]
        if slug == "index":
            slug = os.path.basename(os.path.dirname(filepath))

        if slug in cache:
            # Cache 有但 md 沒寫到 → 補寫進去
            print(f"🔄 從 cache 補寫：{title}")
            post['ai_keywords'] = cache[slug]
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
            updated_count += 1
            continue

        # 呼叫 Gemini
        print(f"🤖 處理中：{title}")
        keywords = get_ai_keywords(post.content, title)

        if keywords:
            # 寫進 md
            post['ai_keywords'] = keywords
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))

            # 同步存進 cache
            cache[slug] = keywords
            save_cache()

            print(f"  ✅ {keywords}")
            updated_count += 1
        else:
            print(f"  ⚠️ 無關鍵字，跳過")

        time.sleep(SLEEP_BETWEEN)

    except Exception as e:
        print(f"❌ 處理失敗 {filepath}：{e}")

print(f"""
━━━━━━━━━━━━━━━━━━━━━━━
✅ 完成！
   新增處理：{updated_count} 篇
   已有跳過：{skip_count} 篇
━━━━━━━━━━━━━━━━━━━━━━━
下一步：
  python scripts/generate_related.py
  hugo --minify
""")
