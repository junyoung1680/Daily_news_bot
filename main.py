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

final_message = "🤖 *오늘의 로이터 심층 뉴스 브리핑 (가독성 테스트)* 🤖\n\n"

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
    
    # 💡 [프롬프트 튜닝] 슬랙 전용 볼드체 문법(*) 적용 및 구조 단순화
    prompt = f"""
    당신은 바쁜 실무자를 위한 IT 뉴스 브리핑 전문가입니다. 
    다음 기사를 원문을 보지 않아도 완벽히 이해할 수 있도록 가독성 최고의 '개조식(글머리 기호)' 형태로 요약하세요. 
    줄글로 길게 풀어쓰는 것을 엄격히 금지합니다.

    [기사 제목]: {title}

    작성 가이드:
    1. 제목: 기사 전체를 아우르는 통찰력 있는 국문 제목을 첫 줄에 작성하세요. 제목의 양끝에는 슬랙에서 굵은 글씨로 보이도록 반드시 별표를 딱 하나씩만 붙이세요. (예시: *지오 플랫폼, IPO 전략 수정으로 자본 확충 선회*)
    2. 소제목 금지: '[분석]', '1. 팩트' 같은 억지스러운 소제목이나 라벨을 절대 쓰지 마세요.
    3. 본문 구조 (반드시 글머리 기호 '•' 사용):
       • (핵심 사건을 명확하게 1~2문장으로 요약)
       • (구체적인 데이터나 주요 기업 동향 기술)
       • (이 사건이 미치는 영향이나 향후 전망 기술, 이때 인과관계나 흐름을 나타내는 화살표 '→' 적극 활용)
    4. 기호 주의: 제목 양끝의 단일 별표(*), 본문의 불릿(•), 화살표(→) 외에 다른 마크다운 기호(#, **, -, 등)나 이모지는 절대 사용하지 마세요.
    5. 출처나 링크 정보는 절대 포함하지 마세요.
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
