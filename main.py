import os
import feedparser
import requests
import json
import time
import google.generativeai as genai

slack_url = os.environ.get("SLACK_URL")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "🤖 *오늘의 로이터 기술 뉴스 요약 (Gemini 2.5 Flash)* 🤖\n\n"

for i in range(5):
    article = feed.entries[i]
    title = article.title
    link = article.link
    
    print(f"\n[{i+1}/5] Gemini가 번역/요약하는 중...")
    prompt = f"다음 영어 기사 제목을 한국어로 깔끔하게 번역하고, 어떤 내용일지 간단히 3줄로 요약해줘.\n\n제목: {title}"
    
    max_retries = 4 # 깃허브 환경을 고려해 재시도 횟수 증가
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
            if '429' in last_error or 'quota' in last_error.lower():
                wait_time = 30
                print(f"⚠️ 깃허브 서버 트래픽 제한 감지. {wait_time}초 대기 중... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                summary = f"(요약 에러 발생: {last_error})"
                break
    
    # 💡 끝내 실패했을 때 단순 '요약 실패'가 아니라 진짜 이유를 슬랙으로 보내도록 수정
    if not summary:
        summary = f"(요약 실패 - 최종 에러: {last_error})"

    final_message += f"*{i+1}. {title}*\n{summary}\n🔗 링크: {link}\n\n---------------------------\n\n"
    
    if i < 4:
        # 💡 구글 서버가 공격으로 오해하지 않도록 기본 휴식 시간을 10초 -> 20초로 대폭 늘림
        print("⏳ 다음 기사로 넘어가기 전 20초 안전 대기...")
        time.sleep(20) 

print("\n🚀 슬랙 전송 중...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 전송 완료!")
