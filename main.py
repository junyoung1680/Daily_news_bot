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

# 💡 [조건 3 & 4] 과거 요약 기록 불러오기 (기억력)
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

# 테스트용: 몇 개의 '새로운' 기사를 요약할 것인지 설정
MAX_ARTICLES = 1  
summarized_count = 0
now_utc = datetime.datetime.now(datetime.timezone.utc)

for article in feed.entries:
    if summarized_count >= MAX_ARTICLES:
        break
        
    title = article.title
    link = article.link
    
    # 💡 [조건 4] 이미 요약했던 기사면 패스
    if link in history:
        continue
        
    # 💡 [조건 2] 24시간이 지난 오래된 기사면 패스
    if hasattr(article, 'published_parsed'):
        pub_dt = datetime.datetime.fromtimestamp(time.mktime(article.published_parsed), datetime.timezone.utc)
        if (now_utc - pub_dt).total_seconds() > 24 * 3600:
            continue

    print(f"\n🔍 새로운 기사 발견: {title}")
    
    # 💡 [조건 5] 원문을 대체할 수준의 상세 요약 프롬프트
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
    
    # 요약 성공한 기사를 기억 장치에 저장
    history.add(link)
    summarized_count += 1
    
    if summarized_count < MAX_ARTICLES:
        time.sleep(10)

# 만약 보낼 새로운 기사가 없다면 종료
if summarized_count == 0:
    print("오늘은 전송할 새로운 기사가 없습니다.")
    final_message = "🤖 오늘은 24시간 이내에 올라온 새로운 로이터 기술 뉴스가 없습니다."

# 💡 [조건 4] 갱신된 기억 장치(history)를 파일로 저장
with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(list(history), f, ensure_ascii=False, indent=2)

# 💡 [조건 1] 9시 정각 발송을 위한 대기 로직 (한국 시간 기준)
now_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# 현재 시간이 아침 8시 대라면, 9시가 될 때까지 코드를 멈추고 기다림
if now_kst.hour == 8:
    print("⏳ 기사 요약 완료! 아침 9시 정각 발송을 위해 대기 중입니다...")
    while True:
        check_kst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
        if check_kst.hour >= 9:
            break
        time.sleep(5) # 5초마다 시간 확인

# 4. 슬랙으로 최종 전송
print("\n🚀 9시 정각! 슬랙 전송 시작...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 슬랙 전송 완료!")
