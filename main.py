import os
import feedparser
import requests
import json
import time
import datetime
import google.generativeai as genai

slack_url = os.environ.get("SLACK_URL")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-3.1-flash-lite')

# ⛔ [테스트 모드] 중복 검사 기능 임시 비활성화
# HISTORY_FILE = "history.json"

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "" 

MAX_ARTICLES = 1  
summarized_count = 0
now_utc = datetime.datetime.now(datetime.timezone.utc)

top_articles = feed.entries[:MAX_ARTICLES]

for article in top_articles:
    title = article.title
    
    if hasattr(article, 'published_parsed'):
        pub_dt = datetime.datetime.fromtimestamp(time.mktime(article.published_parsed), datetime.timezone.utc)
        if (now_utc - pub_dt).total_seconds() > 24 * 3600:
            continue

    print(f"\n🔍 분석 중: {title}")
    
    # 💡 [프롬프트 튜닝] 소제목 제거, 헤더(##)를 통한 폰트 크기/굵기 조절, 자연스러운 흐름 강조
    prompt = f"""
    당신은 IT 산업 전문 전략 분석가입니다. 다음 영문 기사를 분석하여 핵심을 관통하는 브리핑을 작성하세요.
    
    [대상 기사]: {title}
    
    작성 가이드:
    1. 제목 강조: 첫 줄에 기사 전체를 아우르는 통찰력 있는 제목을 작성하세요. 슬랙에서 폰트가 크고 굵게 보이도록 반드시 마크다운 헤더(예: ## **이곳에 제목 작성**)를 사용하세요.
    2. 소제목 및 기호 금지: '[분석]', '[핵심팩트]', '[산업영향]' 같은 소제목이나 대괄호 라벨을 절대 사용하지 마세요. 불필요한 이모지도 모두 빼세요.
    3. 자연스러운 구조: 인위적인 라벨 없이, 글을 읽어 내려가는 것만으로 도입-전개-결과의 구조가 느껴지도록 가독성 좋게 작성하세요.
    4. 화살표(→) 활용: 인과관계(원인→결과)나 상황의 변화(과거→현재)를 나타낼 때는 화살표(→)를 사용하여 정보를 명료하게 연결하세요.
    
    ※ 원문 기사 링크나 출처 정보는 절대 포함하지 마세요.
    """
    
    max_retries = 3
    summary = ""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            summary = response.text
            break 
        except Exception as e:
            if '429' in str(e) or 'quota' in str(e).lower():
                time.sleep(15 * (attempt + 1))
            else:
                break
    
    if not summary:
        summary = "(분석 실패)"

    final_message += f"{summary}\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
    summarized_count += 1

if summarized_count == 0:
    final_message = "🤖 현재 24시간 이내의 새로운 기술 뉴스가 없습니다."

now_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
if now_kst.hour == 8:
    target_kst = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    wait_seconds = (target_kst - now_kst).total_seconds()
    time.sleep(wait_seconds)

print("\n🚀 슬랙 전송 시작...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 슬랙 전송 완료!")
