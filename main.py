import os
import feedparser
import requests
import json
import time
import google.generativeai as genai

# 1. 깃허브 안전 금고에서 키 불러오기
slack_url = os.environ.get("SLACK_URL")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-3.1-flash-lite')

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "🤖 *오늘의 로이터 기술 뉴스 요약 (테스트 모드)* 🤖\n\n"

# 💡 2. 요약할 기사 개수 설정 (테스트가 끝나면 이 숫자만 5로 바꾸면 돼!)
TARGET_COUNT = 1

# 3. 뉴스 요약 진행
for i in range(TARGET_COUNT):
    article = feed.entries[i]
    title = article.title
    link = article.link
    
    print(f"\n[{i+1}/{TARGET_COUNT}] Gemini 3.1 Flash-Lite가 번역/요약하는 중...")
    prompt = f"다음 영어 기사 제목을 한국어로 깔끔하게 번역하고, 어떤 내용일지 간단히 3줄로 요약해줘.\n\n제목: {title}"
    
    max_retries = 3
    summary = ""
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            summary = response.text
            print("✅ 요약 성공!")
            break 
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ 에러 발생 감지: {last_error}")
            
            if '429' in last_error or 'quota' in last_error.lower():
                wait_time = 15 * (attempt + 1)
                print(f"⏳ 서버 쿨다운을 위해 {wait_time}초 대기 후 재시도할게... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                break
    
    if not summary:
        summary = f"(요약 실패 - 최종 에러: {last_error})"

    final_message += f"*{i+1}. {title}*\n{summary}\n🔗 링크: {link}\n\n---------------------------\n\n"
    
    # 마지막 기사가 아닐 때만 10초 대기 (1개일 때는 바로 패스)
    if i < TARGET_COUNT - 1:
        print("⏳ 다음 기사로 넘어가기 전 10초 안전 대기...")
        time.sleep(10) 

# 4. 슬랙으로 최종 전송
print("\n🚀 슬랙 전송 중...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 전송 완료!")
else:
    print(f"❌ 전송 실패: {res.status_code}")
