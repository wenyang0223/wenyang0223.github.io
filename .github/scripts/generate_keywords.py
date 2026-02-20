import os
import frontmatter
import glob
import re
from google import genai  # 新版 import 正確

# ========================
# 配置區（新版 SDK 寫法）
# ========================
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("請設定環境變數 GEMINI_API_KEY，例如在 PowerShell: $env:GEMINI_API_KEY = '你的key'")

client = genai.Client(api_key=api_key)  # ← 這裡建立 client，取代舊的 configure
model_name = "gemini-2.0-flash"  # 或 "gemini-1.5-flash" / "gemini-1.5-pro"

# ========================
# 清理標籤函式
# ========================
def clean_tags(tags_list):
    cleaned = []
    for tag in tags_list:
        t = re.sub(r'["\'\.\s\d\.]', '', tag.strip())
        if t and len(t) <= 12:
            cleaned.append(t)
    return list(set(cleaned))

# ========================
# 呼叫 Gemini 提取關鍵字（新版呼叫方式）
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
    try:
        # 新版 generate_content 寫法：透過 client.models
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt]  # 包成 list 最穩
        )

        # 安全取 text
        if response.candidates and response.candidates[0].content.parts:
            raw_text = response.candidates[0].content.parts[0].text.strip()
        else:
            raw_text = ""

        tags = re.split(r'[,，、\n]', raw_text)
        cleaned = clean_tags(tags)

        # 補足到 5 個
        while len(cleaned) < 5:
            cleaned.append("其他")

        return cleaned[:5]
    except Exception as e:
        print(f"API 呼叫失敗: {e}")
        return []

# ========================
# 主程式
# ========================
files = glob.glob('content/blog/**/*.md', recursive=True)

updated_count = 0

for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)

        if post.get('ai_keywords') or post.get('draft') is True:
            continue

        print(f"正在處理：{filepath}")
        title = post.get('title', '無標題')
        keywords = get_ai_keywords(post.content, title)

        if keywords:
            post['ai_keywords'] = keywords
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
            print(f"成功更新「{title}」 → {keywords}")
            updated_count += 1
        else:
            print(f"無關鍵字生成，跳過：{title}")

    except Exception as e:
        print(f"處理 {filepath} 失敗：{e}")

print(f"\n--- 完成！共更新 {updated_count} 篇文章 ---")
print("記得 git add . && git commit -m 'AI: add ai_keywords' && git push")
