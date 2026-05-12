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
# 설정값
# ─────────────────────────────────────────
MODEL_NAME           = "gemini-3.1-flash-lite"
MAX_ARTICLES         = 5                          
HOURS_RANGE          = 24                         
INTER_CATEGORY_SLEEP = 10                         
RETRY_BASE_SLEEP     = 15                         
MAX_RETRIES          = 3                          
SEND_HOUR_KST        = 9                          

slack_url       = os.environ.get("SLACK_URL")
gemini_api_key  = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel(MODEL_NAME)

now_utc = datetime.datetime.now(datetime.timezone.utc)
now_kst = now_utc + datetime.timedelta(hours=9)

if now_kst.hour == SEND_HOUR_KST - 1:  
    target_kst  = now_kst.replace(hour=SEND_HOUR_KST, minute=0, second=0, microsecond=0)
    wait_seconds = (target_kst - now_kst).total_seconds()
    print(f"⏰ {SEND_HOUR_KST}시 전송을 위해 {int(wait_seconds)}초 대기 중...")
    time.sleep(wait_seconds)
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

print("🌍 AI 중요도 기반 섹션별 뉴스 수집 시작...")

final_message   = "🤖 *오늘의 산업/금융 심층 뉴스 클리핑* 🤖\n\n"
total_summarized = 0

# 💡 [핵심] 아예 기초부터 다시 짠 '무결점 슬랙 포맷터'
def format_for_slack(text: str) -> str:
    # 1. AI가 혹시라도 생성한 잔여 별표(*, **) 마크다운 전량 삭제 (오류 원천 차단)
    text = text.replace('*', '')

    # 2. 괄호 안의 불필요한 공백 제거: [[ 단어 ]] -> [[단어]]
    text = re.sub(r'\[\[\s+(.*?)\s+\]\]', r'[[\1]]', text)

    # 3. 조사가 괄호 밖에 있으면 안으로 강제 편입: [[단어]]조사 -> [[단어조사]]
    text = re.sub(r'\[\[(.*?)\]\]([가-힣]+)', r'[[\1\2]]', text)

    # 4. 슬랙 인식을 위해 [[ ]] 앞뒤로 띄어쓰기(공백) 1칸 강제 확보 
    # (단, 앞이 줄바꿈이거나 뒤가 마침표/쉼표 등 구두점일 경우는 제외하여 깔끔함 유지)
    text = re.sub(r'([^\s\n\[({])\[\[', r'\1 [[', text)
    text = re.sub(r'\]\]([^\s\n.,?!)\]}])', r']] \1', text)

    # 5. 모든 정리가 완벽하게 끝난 [[ ]] 를 슬랙 공식 볼드체인 * * 로 최종 변환
    text = text.replace('[[', '*').replace(']]', '*')

    return text

for display_category, search_keyword in categories.items():
    print(f"\n📂 [{display_category}] 섹션 탐색 및 평가 중...")

    encoded_query = urllib.parse.quote(search_keyword)
    rss_url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    )

    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        print(f"  ⚠️  RSS 파싱 실패 [{display_category}]: {e}")
        continue

    recent_articles = []
    for article in feed.entries:
        if hasattr(article, 'published_parsed') and article.published_parsed:
            pub_ts = calendar.timegm(article.published_parsed)
            pub_dt = datetime.datetime.fromtimestamp(pub_ts, datetime.timezone.utc)

            if (now_utc - pub_dt).total_seconds() > HOURS_RANGE * 3600:
                continue

            pub_kst      = pub_dt + datetime.timedelta(hours=9)
            article_date = f"{pub_kst.month}/{pub_kst.day}"
        else:
            article_date = f"{now_kst.month}/{now_kst.day}"

        recent_articles.append({
            "title": article.title,
            "link":  article.link,
            "date":  article_date,
        })

        if len(recent_articles) >= MAX_ARTICLES:
            break

    if not recent_articles:
        print(f"  ℹ️  [{display_category}] 최근 {HOURS_RANGE}시간 내 기사 없음, 건너뜀")
        continue

    articles_text = ""
    for idx, art in enumerate(recent_articles):
        articles_text += (
            f"[{idx+1}] 제목: {art['title']}\n"
            f"    링크: {art['link']}\n"
            f"    발행일: {art['date']}\n\n"
        )

    if display_category in ["대출", "부동산"]:
        target_instruction = (
            "이 섹션은 매우 중요합니다. "
            "후보 기사 중 가장 파급력이 큰 3개의 기사를 반드시 선정하여 요약하세요. "
            "(후보가 3개 이하라면 모두 요약하세요.)"
        )
    else:
        target_instruction = (
            "당신이 판단하기에 시장 파급력과 중요도가 높은 기사만 선별하세요. "
            "1개에서 최대 3개까지만 골라서 요약하면 됩니다."
        )

    # 💡 [프롬프트] 별표(*) 사용을 전면 금지하고, 고유 식별자인 대괄호 [[ ]] 사용 강제
    prompt = f"""
당신은 금융, 부동산, 통신 산업 전문 수석 애널리스트입니다.
아래 [후보 기사 목록]을 읽고, 선별 기준에 따라 중요한 기사만 뽑아 요약하세요.

[선별 기준]: {target_instruction}

[후보 기사 목록]
{articles_text}
[작성 양식 및 규칙 - 절대 엄수]
섹션 이름(예: [대출])은 절대 출력하지 말고 바로 기사 제목부터 시작하세요.

기사 제목 (발행일)
• 정책방향: 핵심 내용 아주 간결하게 작성 → 파급효과
• 주요동향: 기업 동향이나 핵심 데이터 간결하게 작성 → 결과
• 시장반응: 시장 영향 간결하게 작성 → 향후 전망
🔗 원문 링크: (반드시 후보 기사 목록에 있는 링크를 그대로 복사하세요.)

[강조 규칙 - 반드시 지킬 것]
1. 본문 내용 중 강조하고 싶은 주체(기업/기관)나 핵심 숫자는 반드시 대괄호 두 개 [[ ]] 로 감싸세요.
  (예: [[카카오뱅크]], [[1.1조원]])
2. 마크다운 별표(*)나 기타 기호는 절대 사용하지 마세요. 오직 [[ ]] 만 사용해야 합니다.
3. 여러 기사를 요약할 때는 기사 사이에 빈 줄을 하나 넣으세요.
"""

    summary = ""
    for attempt in range(MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            summary  = response.text.strip()

            if summary and "(분석 실패)" not in summary:
                # 💡 파이썬 컴파일러 작동: AI의 텍스트를 슬랙 공식 포맷으로 완벽하게 클렌징 및 변환
                summary = format_for_slack(summary)

                # 기사 제목 첫 줄 무조건 굵은 글씨(*) 처리
                blocks = summary.split('\n\n')
                formatted_blocks = []
                for block in blocks:
                    lines = block.strip().split('\n')
                    if lines:
                        # 이미 치환 과정에서 남은 기호가 있다면 깨끗이 제거 후 감싸기
                        first_line  = lines[0].replace('*', '').replace('[', '').replace(']', '').strip()
                        lines[0]    = f"*{first_line}*"
                        formatted_blocks.append('\n'.join(lines))

                summary = '\n\n'.join(formatted_blocks)
            break

        except Exception as e:
            if '429' in str(e) or 'quota' in str(e).lower():
                wait = RETRY_BASE_SLEEP * (attempt + 1)
                print(f"  ⏳ Rate limit, {wait}초 후 재시도 ({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                print(f"  ❌ Gemini 오류 [{display_category}]: {e}")
                break

    if summary and "(분석 실패)" not in summary:
        final_message   += f"📌 *[{display_category}]*\n{summary}\n\n"
        total_summarized += 1
        print(f"  ✅ [{display_category}] 요약 완료")
    else:
        print(f"  ⚠️  [{display_category}] 요약 실패 또는 결과 없음")

    time.sleep(INTER_CATEGORY_SLEEP)


if total_summarized == 0:
    final_message = "🤖 현재 새로운 산업/금융 뉴스가 없습니다."

# Slack 메시지 길이 체크 (Webhook 한도: ~40,000자)
if len(final_message) > 39000:
    final_message = final_message[:39000] + "\n\n⚠️ 메시지가 너무 길어 일부가 잘렸습니다."

print("\n🚀 슬랙 전송 시작...")
slack_data = {"text": final_message}
res = requests.post(
    slack_url,
    headers={"Content-Type": "application/json"},
    data=json.dumps(slack_data, ensure_ascii=False),
)

if res.status_code == 200:
    print("✅ 슬랙 전송 완료!")
else:
    print(f"❌ 슬랙 전송 실패: {res.status_code} / {res.text}")
