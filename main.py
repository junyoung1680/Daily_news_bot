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
# 설정값 (속도와 안정성 최적화)
# ─────────────────────────────────────────
MODEL_NAME           = "gemini-3.1-flash-lite"
MAX_ARTICLES         = 5                          
HOURS_RANGE          = 24                         
MAX_RETRIES          = 2  # 무한 대기 방지를 위해 재시도 2회로 단축
RETRY_BASE_SLEEP     = 5  # 대기 시간 5초로 대폭 단축

slack_url       = os.environ.get("SLACK_URL")
gemini_api_key  = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel(MODEL_NAME)

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

print(f"🚀 뉴스 수집 시작 (실행시각: {now_kst.strftime('%H:%M:%S')})")
final_message = f"🤖 *산업/금융 뉴스 클리핑* ({now_kst.strftime('%m/%d %H:%M')})\n\n"
total_summarized = 0

for display_category, search_keyword in categories.items():
    print(f"\n📂 [{display_category}] 섹션 처리 중...")
    encoded_query = urllib.parse.quote(search_keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

    # 안전장치 1: RSS 호출 시 최대 10초만 기다리고 포기 (무한 대기 방지)
    try:
        response = requests.get(rss_url, timeout=10)
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"  ⚠️ RSS 호출 실패 (통신 지연): {e}")
        continue

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

    if not recent_articles: 
        print("  ℹ️ 최근 24시간 내 유효한 기사 없음.")
        continue

    articles_text = ""
    for idx, art in enumerate(recent_articles):
        articles_text += f"[{idx+1}] 제목: {art['title']}\n    링크: {art['link']}\n    발행일: {art['date']}\n\n"

    prompt = f"""
당신은 금융/산업 전문 수석 애널리스트입니다. 아래 기사 목록 중 가장 중요한 기사 1~3개를 선정하여 요약하세요.

[후보 기사 목록]
{articles_text}

[작성 규칙 - 필독]
1. 각 기사 요약은 아래 양식을 엄격히 따르세요:
   기사 제목 (발행일)
   • 정책방향: 핵심 내용 요약 → 파급효과
   • 주요동향: 관련 기업이나 시장의 움직임 요약
   • 시장반응: 업계나 소비자의 반응 및 향후 전망
   🔗 원문 링크: (기사 링크)

2. 강조 규칙: 강조하고 싶은 주체나 숫자는 반드시 [[ ]]로 감싸세요. (예: [[카카오뱅크는]])
3. 별표(*)는 절대 사용하지 마세요. (코드에서 자동으로 처리합니다)
"""

    summary = ""
    print("  ⏳ AI 요약 생성 요청 중...")
    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            summary = format_for_slack(response.text.strip())
            
            blocks = summary.split('\n\n')
            formatted_blocks = []
            for block in blocks:
                lines = block.strip().split('\n')
                if lines:
                    lines[0] = f"*{lines[0].replace('*', '')}*"
                    formatted_blocks.append('\n'.join(lines))
            summary = '\n\n'.join(formatted_blocks)
            print("  ✅ AI 요약 완료!")
            break
        except Exception as e:
            # 안전장치 2: 어떤 에러 때문에 막히는지 실시간 출력
            print(f"  ⚠️ AI 호출 에러 ({attempt+1}/{MAX_RETRIES}): {e}")
            if "finish_reason" in str(e) or "safety" in str(e).lower():
                print("  🚫 보안/검열 필터에 걸려 요약 불가. 다음 섹션으로 넘어갑니다.")
                break # 안전 필터에 걸리면 재시도해도 안 되므로 즉시 중단
            time.sleep(RETRY_BASE_SLEEP)
            summary = ""

    if summary:
        final_message += f"📌 *[{display_category}]*\n{summary}\n\n"
        total_summarized += 1
        
    time.sleep(2) # API 호출 제한 방지를 위한 짧은 휴식

if total_summarized == 0:
    final_message = "🤖 현재 새로운 뉴스가 없습니다."

# 안전장치 3: 슬랙 전송 시 무한 대기 방지
print("\n🚀 슬랙 전송 시도 중...")
try:
    res = requests.post(slack_url, data=json.dumps({"text": final_message}), timeout=10)
    if res.status_code == 200:
        print("✅ 전송 완벽 성공!")
    else:
        print(f"❌ 슬랙 전송 실패 (상태 코드: {res.status_code})")
except Exception as e:
    print(f"❌ 슬랙 서버 통신 에러: {e}")
