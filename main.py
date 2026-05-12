import os
import feedparser
import requests
import json
import time
import datetime
import urllib.parse
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
        
    # 💡 [수정] 기사가 아예 없다면 '동향 없음' 텍스트를 남기지 않고 조용히 패스
    if not recent_articles:
        continue

    articles_text = ""
    for idx, art in enumerate(recent_articles):
        articles_text += f"[{idx+1}] 제목: {art['title']}\n    링크: {art['link']}\n    발행일: {art['date']}\n\n"

    if display_category in ["대출", "부동산"]:
        target_instruction = "이 섹션은 매우 중요합니다. 후보 기사 중 가장 파급력이 큰 3개의 기사를 반드시 선정하여 요약하세요. (후보가 3개 이하라면 모두 요약하세요.)"
    else:
        target_instruction = "당신이 판단하기에 시장 파급력과 중요도가 높은 기사만 선별하세요. 1개에서 최대 3개까지만 골라서 요약하면 됩니다."

    # 💡 [프롬프트 튜닝] 제미나이가 카테고리명을 중복해서 쓰지 않도록 지침 변경
    prompt = f"""
    당신은 금융, 부동산, 통신 산업 전문 수석 애널리스트입니다. 
    아래 [후보 기사 목록]을 읽고, 선별 기준에 따라 중요한 기사만 뽑아 사용자의 '뉴스 클리핑 양식'에 맞춰 요약하세요.
    
    [선별 기준]: {target_instruction}

    [후보 기사 목록]
    {articles_text}

    [작성 양식 및 규칙] - 선정된 각 기사마다 아래 형식을 100% 똑같이 반복해서 작성하세요. 여러 기사를 요약할 때는 기사와 기사 사이에 빈 줄을 하나 넣어 구분하세요.
    ※ 주의: 섹션 이름(예: 📌 [대출])은 절대 출력하지 마세요. 바로 기사 제목부터 시작하세요.

    *통찰력 있는 기사 제목 (발행일)*
    • 핵심단어: 사건의 핵심 내용 기술 → 파급효과나 향후 전망
    • 핵심단어: 주요 기업 동향이나 구체적인 데이터 기술 → 결과
    • 핵심단어: 시장 영향이나 소비자 변화 기술 → 결과
    🔗 원문 링크: (반드시 후보 기사 목록에 있는 링크를 그대로 정확하게 복사하세요.)

    [세부 지침]
    1. 제목: 전체를 아우르는 통찰력 있는 제목을 짓고, 끝에 발행일을 넣은 뒤 전체를 단일 별표(*)로 감싸 굵은 글씨로 만드세요.
    2. 불릿(•) 시작: 각 문장은 '정책방향:', '시장반응:', '공급실적:' 처럼 [핵심단어:] 로 시작하세요.
    3. 🌟강조(가장 중요)🌟: 본문 내용 중 '중요한 주체'나 '핵심 숫자'를 단일 별표(*)로 강조하세요. 
       [슬랙 굵은글씨 규칙]:
       - 별표와 단어 사이에 절대 공백을 넣지 마세요. (오류: * 카카오 *, 정상: *카카오*)
       - 조사(은/는/이/가/을/를 등)는 가독성을 위해 절대 별표 안에 넣지 말고 밖으로 빼서 쓰세요. 단, 별표와 띄어쓰기 없이 바로 붙여 써야 합니다. (예: *카카오뱅크*는 중저신용대출 누적 *1.1조원*을 공급)
    4. 화살표(→): 원인과 결과를 나타낼 때 화살표를 적극 사용하세요.
    5. 기호 주의: 슬랙 굵은 글씨용 단일 별표(*), 불릿(•), 화살표(→) 외에 다른 마크다운 기호(#, ** 등)는 절대 사용하지 마세요.
    """
    
    max_retries = 3
    summary = ""
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            summary = response.text
            break 
        except Exception as e:
            if '429' in str(e) or 'quota' in str(e).lower():
                time.sleep(15 * (attempt + 1))
            else:
                break
    
    # 💡 [수정] 요약이 성공적으로 나왔을 때만, 파이썬 코드 단에서 머리말을 딱 한 번 붙여줌
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
