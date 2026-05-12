import os
import calendar
import feedparser
import requests
import json
import time
import datetime
import urllib.parse
import re
import google.generativeai as genai

# ─────────────────────────────────────────
# 설정값 (테스트를 위해 13시 30분으로 세팅)
# ─────────────────────────────────────────
MODEL_NAME           = "gemini-3.1-flash-lite"
MAX_ARTICLES         = 5                          
HOURS_RANGE          = 24                         
INTER_CATEGORY_SLEEP = 10                         
RETRY_BASE_SLEEP     = 15                         
MAX_RETRIES          = 3                          
SEND_HOUR_KST        = 13  # ⬅️ 테스트를 위해 13시로 변경
SEND_MINUTE_KST      = 30  # ⬅️ 테스트를 위해 30분으로 설정

slack_url       = os.environ.get("SLACK_URL")
gemini_api_key  = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel(MODEL_NAME)

now_utc = datetime.datetime.now(datetime.timezone.utc)
now_kst = now_utc + datetime.timedelta(hours=9)

# 💡 테스트용 정밀 대기 로직
target_kst = now_kst.replace(hour=SEND_HOUR_KST, minute=SEND_MINUTE_KST, second=0, microsecond=0)

# 만약 현재 시간이 설정된 시간보다 이전이라면, 그 시간까지 대기합니다.
if now_kst < target_kst:
    wait_seconds = (target_kst - now_kst).total_seconds()
    print(f"⏰ {SEND_HOUR_KST}:{SEND_MINUTE_KST} 전송을 위해 {int(wait_seconds)}초 대기 중...")
    time.sleep(wait_seconds)
    # 대기 후 현재 시간 갱신
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = now_utc + datetime.timedelta(hours=9)

categories = {
    "대출":   "신용대출 OR 가계대출 OR 대환대출 OR 대출규제 OR 카드론 OR 정책대출",
    "부동산": "주택담보대출 OR 주담대 OR 전세대출 OR 전세자금대출",
    "계좌":   "파킹통장 OR 예적금 OR 은행사 OR 통장개설 OR 시중은행 OR 지방은행",
    "카드":   "신용카드 OR 체크카드 OR 카드발급 OR PLCC OR 신한카드 OR 국민카드 OR 삼성카드 OR 현대카드",
    "보험":   "보험사 OR 보험규제 OR 보험중개 OR 방카슈랑스 OR 손해보험 OR 생명보험",
    "자동차": "오토론 OR 자동차대출 OR 자동차할부 OR 장기렌트 OR 자동차금융",
    "모바일": "통신사 OR 이통3사 OR 알뜰폰 OR 번호이동 OR 모바일가입",
    "업권":   "금융당국 OR 금융위 OR 금감원 OR 인터넷은행 OR 카카오뱅크 OR 네이버페이 OR 토스 OR 핀테크",
}

def format_for_slack(text: str) -> str:
    text = text.replace('*', '')
    text = re.sub(r'\[\[\s+(.*?)\s+\]\]', r'[[\1]]', text)
    text = re.sub(r'\[\[(.*?)\]\]([가-힣]+)', r'[[\1\2]]', text)
    text = re.sub(r'([^\s\n\[({])\[\[', r'\1 [[', text)
    text = re.sub(r'\]\]([^\s\n.,?!)\]}])', r']] \1', text)
    text = text.replace('[[', '*').replace(']]', '*')
    return text

print("🌍 뉴스 수집 및 분석 시작...")

final_message   = "🤖 *[테스트] 오늘의 산업/금융 심층 뉴스 클리핑* 🤖\n\n"
total_summarized = 0

for display_category, search_keyword in categories.items():
    encoded_query = urllib.parse.quote(search_keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

    try:
        feed = feedparser.parse(rss_url)
    except: continue

    recent_articles = []
    for article in feed.entries:
        if hasattr(article, 'published_parsed') and article.published_parsed:
            pub_ts = calendar.timegm(article.published_parsed)
            pub_dt = datetime.datetime.fromtimestamp(pub_ts, datetime.timezone.utc)
            if (now_utc - pub_dt).total_seconds() > HOURS_RANGE * 3600: continue
            pub_kst = pub_dt + datetime.timedelta(hours=9)
            date_str = f"{pub_kst.month}/{pub_kst.day}"
        else: date_str = f"{now_kst.month}/{now_kst.day}"

        recent_articles.append({"title": article.title, "link": article.link, "date": date_str})
        if len(recent_articles) >= MAX_ARTICLES: break

    if not recent_articles: continue

    articles_text = ""
    for idx, art in enumerate(recent_articles):
        articles_text += f"[{idx+1}] 제목: {art['title']}\n    링크: {art['link']}\n    발행일: {art['date']}\n\n"

    target_instruction = "가장 중요한 1~3개의 기사를 선정하여 요약하세요."
    prompt = f"""
당신은 금융/산업 수석 애널리스트입니다. 아래 기사 중 중요한 것을 선별해 요약하세요.
[선별 기준]: {target_instruction}
[후보 기사 목록]
{articles_text}
[작성 양식]
기사 제목 (발행일)
• 핵심내용: 간결하게 작성 → 파급효과
🔗 원문 링크: (링크 복사)

[주의] 강조하고 싶은 단어는 반드시 [[ ]] 로 감싸세요. (예: [[카카오뱅크]]) 별표(*)는 절대 쓰지 마세요.
"""

    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            summary  = format_for_slack(response.text.strip())
            
            # 제목 굵게 처리
            blocks = summary.split('\n\n')
            formatted_blocks = []
            for block in blocks:
                lines = block.strip().split('\n')
                if lines:
                    lines[0] = f"*{lines[0].replace('*', '')}*"
                    formatted_blocks.append('\n'.join(lines))
            summary = '\n\n'.join(formatted_blocks)
            break
        except:
            time.sleep(RETRY_BASE_SLEEP)
            summary = ""

    if summary:
        final_message += f"📌 *[{display_category}]*\n{summary}\n\n"
        total_summarized += 1

if total_summarized == 0:
    final_message = "🤖 현재 새로운 뉴스가 없습니다."

requests.post(slack_url, data=json.dumps({"text": final_message}))
print("✅ 완료")
