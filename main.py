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

final_message = "" # 제목을 제미나이가 지으므로 상단 고정 제목 제거

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
    
    # 💡 [프롬프트 튜닝] 불필요한 정보 제거 및 인과관계 강조
    prompt = f"""
    당신은 IT 산업 전문 전략 분석가입니다. 다음 영문 기사를 분석하여 핵심을 관통하는 브리핑을 작성하세요.
    
    [대상 기사]: {title}
    
    작성 가이드:
    1. 제목: 원문 제목을 번역하지 말고, 기사 전체 내용을 아우르는 '인사이트 중심의 새로운 제목'을 지으세요. (예: [분석] OO 기업의 전략 변화와 시장 영향)
    2. 기호 사용: 불필요한 이모지나 장식용 기호는 모두 제거하세요. 
    3. 화살표 활용: 인과관계(원인→결과)나 시간 순서(과거→현재)가 명확한 설명에만 화살표(→)를 사용하여 명료하게 기술하세요.
    4. 구조 (간결하게):
       - [핵심 팩트]: 사건의 본질을 데이터와 사실 위주로 기술
       - [산업 영향]: 업계에 미칠 파급 효과 및 향후 전망
    
    ※ 주의: 원문 기사 링크나 출처 정보는 절대 포함하지 마세요.
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

    # 💡 링크를 제외하고 요약본만 메시지에 담음
    final_message += f"{summary}\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
    summarized_count += 1

if summarized_count == 0:
    final_message = "🤖 현재 24시간 이내의 새로운 기술 뉴스가 없습니다."

# 9시 정각 발송 대기 로직
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
