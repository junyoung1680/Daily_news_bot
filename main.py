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

# ⛔ [테스트 모드] 중복 검사용 기억장치 기능 임시 비활성화
# HISTORY_FILE = "history.json"
# if os.path.exists(HISTORY_FILE):
#     with open(HISTORY_FILE, "r", encoding="utf-8") as f:
#         history = set(json.load(f))
# else:
#     history = set()

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "🤖 *오늘의 로이터 심층 뉴스 브리핑 (가독성 테스트)* 🤖\n\n"

MAX_ARTICLES = 1  
summarized_count = 0
now_utc = datetime.datetime.now(datetime.timezone.utc)

top_articles = feed.entries[:MAX_ARTICLES]

for article in top_articles:
    title = article.title
    link = article.link
    
    if hasattr(article, 'published_parsed'):
        pub_dt = datetime.datetime.fromtimestamp(time.mktime(article.published_parsed), datetime.timezone.utc)
        if (now_utc - pub_dt).total_seconds() > 24 * 3600:
            print(f"⏰ 24시간이 지난 기사입니다 (패스): {title}")
            continue

    print(f"\n🔍 새로운 기사 발견: {title}")
    
    # 💡 [프롬프트 튜닝] 가독성과 정보 밀도에 완전히 집중한 새로운 명령어
    prompt = f"""
    당신은 바쁜 실무자를 위한 IT 뉴스 브리핑 전문가입니다. 
    다음 영문 기사 제목을 바탕으로, 원문을 보지 않아도 내용을 파악할 수 있으면서도 '모바일 슬랙 환경'에서 가독성이 좋게 요약해 주세요.
    장황한 수식어, 불필요한 서론/결론은 전부 빼고, 핵심 정보만 밀도 있게 전달해야 합니다.

    [기사 제목]: {title}
    
    아래 마크다운 양식을 엄격히 지켜서 건조하고 명확한 어투로 작성하세요:

    💡 **[한국어 번역 기사 제목]** **1. 팩트 체크 (What Happened)**
    • (핵심 사건을 간결하고 명확하게 1~2문장으로 설명)
    • (관련된 주요 기업, 인물, 수치 등 구체적인 데이터 포함)

    **2. 관전 포인트 (Why it matters)**
    • (이 사건이 시장/업계에 미치는 파급력이나 배경을 1~2문장으로 압축 설명)
    • (향후 예상되는 흐름이나 우리가 주목해야 할 점)
    """
    # -------------------------------------------------------------------------
    
    max_retries = 3
    summary = ""
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            summary = response.text
            print("✅ 심층 요약 성공!")
            break 
        except Exception as e:
            last_error = str(e)
            if '429' in last_error or 'quota' in last_error.lower():
                time.sleep(15 * (attempt + 1))
            else:
                break
    
    if not summary:
        summary = f"(요약 실패 - 최종 에러: {last_error})"

    final_message += f"{summary}\n\n🔗 원문 링크: {link}\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    summarized_count += 1

if summarized_count == 0:
    print("오늘은 전송할 새로운 기사가 없습니다.")
    final_message = "🤖 오늘은 24시간 이내에 올라온 새로운 로이터 기술 뉴스가 없습니다."

now_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
if now_kst.hour == 8:
    target_kst = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    wait_seconds = (target_kst - now_kst).total_seconds()
    print(f"⏳ 9시 정각 발송을 위해 {int(wait_seconds)}초 대기합니다...")
    time.sleep(wait_seconds)

print("\n🚀 슬랙 전송 시작...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 슬랙 전송 완료!")
