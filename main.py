import os
import feedparser
import requests
import json
import time
import google.generativeai as genai

slack_url = os.environ.get("SLACK_URL")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
# 1번 요약에 성공했던 모델 유지
model = genai.GenerativeModel('gemini-2.5-flash')

print("🌍 뉴스 수집 중...")
rss_url = "https://news.google.com/rss/search?q=technology+source:reuters&hl=en-US&gl=US&ceid=US:en"
feed = feedparser.parse(rss_url)

final_message = "🤖 *오늘의 로이터 기술 뉴스 요약* 🤖\n\n"

for i in range(5):
    article = feed.entries[i]
    title = article.title
    link = article.link
    
    print(f"\n[{i+1}/5] Gemini가 번역/요약하는 중...")
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
            
            # 서버 제한에 걸리면 확실하게 1분을 쉬고 재시도
            if '429' in last_error or 'quota' in last_error.lower() or 'exhausted' in last_error.lower():
                print(f"⏳ 서버 쿨다운을 위해 60초 대기 후 재시도합니다... ({attempt+1}/{max_retries})")
                time.sleep(60)
            else:
                break
    
    if not summary:
        summary = f"(요약 실패 - 최종 에러: {last_error})"

    final_message += f"*{i+1}. {title}*\n{summary}\n🔗 링크: {link}\n\n---------------------------\n\n"
    
    # 💡 [핵심] 분당 요청 횟수(RPM) 초과를 절대적으로 막기 위해 무조건 60초 안전 대기
    if i < 4:
        print("⏳ RPM 제한 방지를 위해 다음 기사까지 60초 대기합니다...")
        time.sleep(60) 

print("\n🚀 슬랙 전송 중...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 전송 완료!")
