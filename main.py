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

# 💡 [보완] URL 대신 절대 변하지 않는 '기사 제목(Title)'으로 중복 검사
HISTORY_FILE = "history.json"
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = set(json.load(f))
else:
    history = set()

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "🤖 *오늘의 로이터 심층 뉴스 브리핑* 🤖\n\n"

MAX_ARTICLES = 1  
summarized_count = 0
now_utc = datetime.datetime.now(datetime.timezone.utc)

# 💡 [보완] 루프가 무한히 다음 기사를 찾는 것을 막기 위해, 최상위 N개만 딱 잘라서 검사
top_articles = feed.entries[:MAX_ARTICLES]

for article in top_articles:
    title = article.title
    link = article.link
    
    # [조건 4] 기억장치에 있는 제목이면 완전히 패스
    if title in history:
        print(f"🔄 이미 발송된 기사입니다 (패스): {title}")
        continue
        
    # [조건 2] 24시간이 지난 기사면 패스
    if hasattr(article, 'published_parsed'):
        pub_dt = datetime.datetime.fromtimestamp(time.mktime(article.published_parsed), datetime.timezone.utc)
        if (now_utc - pub_dt).total_seconds() > 24 * 3600:
            print(f"⏰ 24시간이 지난 기사입니다 (패스): {title}")
            continue

    print(f"\n🔍 새로운 기사 발견: {title}")
    
    # [조건 5] 심층 요약 프롬프트
    prompt = f"""
    당신은 IT 전문 수석 기자입니다. 다음 영문 기사 제목을 바탕으로, 독자가 원문을 전혀 읽지 않아도 이 사안을 완벽하게 이해할 수 있도록 상세한 심층 브리핑을 작성해 주세요.
    
    [기사 제목]: {title}
    
    아래 양식을 지켜주세요:
    1. 핵심 요약 (한 줄 펀치라인)
    2. 상세 내용 (무슨 일이 일어났는지, 주요 팩트 위주로 3~4개 글머리 기호 사용)
    3. 배경 및 파급 효과 (왜 이 사건이 중요하며, 향후 IT 시장이나 기업에 어떤 영향을 미칠지)
    """
    
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

    final_message += f"📰 *{title}*\n\n{summary}\n\n🔗 원문 링크: {link}\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # 요약에 성공한 '제목'을 기억 장치에 추가
    history.add(title)
    summarized_count += 1

# 중복/시간 초과로 요약된 기사가 하나도 없을 경우의 메시지
if summarized_count == 0:
    print("오늘은 전송할 새로운 기사가 없습니다.")
    final_message = "🤖 오늘은 24시간 이내에 올라온 새로운 로이터 기술 뉴스가 없습니다."

# 갱신된 기억장치 저장
with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(list(history), f, ensure_ascii=False, indent=2)

# 💡 [보완] 9시 정각을 위한 정확한 타이머 수면 로직
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
