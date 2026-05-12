import os
import feedparser
import requests
import json
import time
import datetime
import urllib.parse
import re
import google.generativeai as genai

slack_url = os.environ.get("SLACK_URL")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-3.1-flash-lite')

print("🌍 AI 중요도 기반 섹션별 뉴스 수집 시작...")

categories = {
    "대출": "신용대출 OR 가계대출 OR 대환대출 OR 대출규제 OR 카드론 OR 정책대출",
    "부동산": "주택담보대출 OR 주담대 OR 전세대출 OR 전세자금대출",
    "계좌": "파킹통장 OR 예적금 OR 은행사 OR 통장개설 OR 시중은행 OR 지방은행",
    "카드": "신용카드 OR 체크카드 OR 카드발급 OR PLCC OR 신한카드 OR 국민카드 OR 삼성카드 OR 현대카드",
    "보험": "보험사 OR 보험규제 OR 보험중개 OR 방카슈랑스 OR 손해보험 OR 생명보험",
    "자동차": "오토론 OR 자동차대출 OR 자동차할부 OR 장기렌트 OR 자동차금융",
    "모바일": "통신사 OR 이통3사 OR 알뜰폰 OR 번호이동 OR 모바일가입",
    "업권": "금융당국 OR 금융위 OR 금감원 OR 인터넷은행 OR 카카오뱅크 OR 네이버페이 OR 토스 OR 핀테크"
}

final_message = "🤖 *오늘의 산업/금융 심층 뉴스 클리핑* 🤖\n\n"

now_utc = datetime.datetime.now(datetime.timezone.utc)
now_kst = now_utc + datetime.timedelta(hours=9)
total_summarized = 0

for display_category, search_keyword in categories.items():
    print(f"\n📂 [{display_category}] 섹션 탐색 및 평가 중...")
    encoded_query = urllib.parse.quote(search_keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    feed = feedparser.parse(rss_url)
    
    recent_articles = []
    for article in feed.entries:
        if len(recent_articles) >= 5:
            break
            
        if hasattr(article, 'published_parsed'):
            pub_dt = datetime.datetime.fromtimestamp(time.mktime(article.published_parsed), datetime.timezone.utc)
            if (now_utc - pub_dt).total_seconds() > 24 * 3600:
                continue 
            
            pub_kst = pub_dt + datetime.timedelta(hours=9)
            article_date = f"{pub_kst.month}/{pub_kst.day}"
        else:
            article_date = f"{now_kst.month}/{now_kst.day}"

        recent_articles.append({
            "title": article.title,
            "link": article.link,
            "date": article_date
        })
        
    if not recent_articles:
        continue

    articles_text = ""
    for idx, art in enumerate(recent_articles):
        articles_text += f"[{idx+1}] 제목: {art['title']}\n    링크: {art['link']}\n    발행일: {art['date']}\n\n"

    if display_category in ["대출", "부동산"]:
        target_instruction = "이 섹션은 매우 중요합니다. 후보 기사 중 가장 파급력이 큰 3개의 기사를 반드시 선정하여 요약하세요. (후보가 3개 이하라면 모두 요약하세요.)"
    else:
        target_instruction = "당신이 판단하기에 시장 파급력과 중요도가 높은 기사만 선별하세요. 1개에서 최대 3개까지만 골라서 요약하면 됩니다."

    # 💡 [프롬프트 복구] AI가 가장 잘 이해하는 마크다운(*)으로 복구하여 환각(오류) 방지
    prompt = f"""
    당신은 금융, 부동산, 통신 산업 전문 수석 애널리스트입니다. 
    아래 [후보 기사 목록]을 읽고, 선별 기준에 따라 중요한 기사만 뽑아 요약하세요.
    
    [선별 기준]: {target_instruction}
    [후보 기사 목록]
    {articles_text}

    [작성 양식 및 규칙 - 절대 엄수]
    섹션 이름(예: [대출])은 절대 출력하지 말고 바로 기사 제목부터 시작하세요.

    *통찰력 있는 기사 제목 (발행일)*
    • 정책방향: 핵심 내용 아주 간결하게 작성 → 파급효과
    • 주요동향: 기업 동향이나 핵심 데이터 간결하게 작성 → 결과
    • 시장반응: 시장 영향 간결하게 작성 → 향후 전망
    🔗 원문 링크: (반드시 후보 기사 목록에 있는 링크를 그대로 복사하세요.)

    [세부 지침]
    1. 제목: 양 끝에 단일 별표(*)를 붙여 굵은 글씨로 만드세요.
    2. 강조: 본문에서 강조하고 싶은 주체(기업/기관)나 숫자는 단일 별표(*)로 감싸세요. 조사는 별표 바로 뒤에 붙여 쓰세요. (예: *카카오뱅크*는 중저신용대출 *1.1조원*을 공급)
    3. 여러 기사를 요약할 때는 기사와 기사 사이에 빈 줄을 하나 넣으세요.
    """
    
    max_retries = 3
    summary = ""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            summary = response.text.strip()
            
            if summary and "(분석 실패)" not in summary:
                # 안전장치: 혹시 AI가 ** 를 썼다면 * 로 일괄 정리
                summary = summary.replace('**', '*')
                
                # 💡 [최종 해결 로직] 슬랙 마크다운 한계 극복
                # AI가 "*우리은행*은" 이라고 출력하면, 파이썬이 "*우리은행은*" 으로 강제 변환합니다.
                # 공백(띄어쓰기) 없이 슬랙에서 100% 굵은 글씨로 적용되게 만드는 유일한 방법입니다.
                summary = re.sub(r'\*([^*]+)\*([가-힣]+)', r'*\1\2*', summary)
                
            break 
            
        except Exception as e:
            if '429' in str(e) or 'quota' in str(e).lower():
                time.sleep(15 * (attempt + 1))
            else:
                break
    
    if summary and "(분석 실패)" not in summary:
        final_message += f"📌 *[{display_category}]*\n{summary}\n\n"
        total_summarized += 1
    
    time.sleep(10)

if total_summarized == 0:
    final_message = "🤖 현재 새로운 산업/금융 뉴스가 없습니다."

if now_kst.hour == 8:
    target_kst = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    wait_seconds = (target_kst - now_kst).total_seconds()
    time.sleep(wait_seconds)

print("\n🚀 슬랙 전송 시작...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 슬랙 전송 완료!")
