import os
import feedparser
import requests
import json
import time
import google.generativeai as genai

slack_url = os.environ.get("SLACK_URL")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
# 💡 네가 원했던, 그리고 가장 잘 작동했던 2.5 버전으로 픽스
model = genai.GenerativeModel('gemini-2.5-flash')

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "🤖 *오늘의 로이터 기술 뉴스 요약 (Gemini 2.5 Flash)* 🤖\n\n"

for i in range(5):
    article = feed.entries[i]
    title = article.title
    link = article.link
    
    print(f"\n[{i+1}/5] Gemini 2.5 Flash가 번역/요약하는 중...")
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
            
            # 💡 [핵심] 하루 20회 한도를 다 썼다면 무의미한 재시도를 멈춤
            if 'GenerateRequestsPerDay' in last_error or 'limit: 20' in last_error:
                print("🚫 일일 무료 제공량(20회)을 모두 소진했습니다.")
                summary = f"(요약 실패 - 일일 무료 한도 20회 초과. 내일 다시 시도해야 합니다.)"
                break 
                
            # 분당 트래픽 제한(429)일 경우에만 대기 후 재시도
            elif '429' in last_error or 'quota' in last_error.lower():
                wait_time = 15
                print(f"⚠️ 분당 제한 감지. {wait_time}초 대기 중... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                summary = f"(요약 에러: {last_error})"
                break
    
    if not summary:
        summary = f"(요약 실패 - 최종 에러: {last_error})"

    final_message += f"*{i+1}. {title}*\n{summary}\n🔗 링크: {link}\n\n---------------------------\n\n"
    
    if i < 4:
        time.sleep(10)

print("\n🚀 슬랙 전송 중...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 전송 완료!")
