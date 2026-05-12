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

# ⛔ [테스트 모드] 중복 검사 기능 임시 비활성화
# HISTORY_FILE = "history.json"

print("🌍 뉴스 수집 중...")

keywords = "대출 OR 부동산 OR 계좌 OR 카드 OR 보험 OR 자동차 OR 통신사 OR 알뜰폰 OR 금융업권"
encoded_query = urllib.parse.quote(keywords)
rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"

feed = feedparser.parse(rss_url)

final_message = "" 

# 💡 1. 검증을 위해 기사 요약 개수를 2개로 세팅
MAX_ARTICLES = 2  
summarized_count = 0
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_kst = now_utc + datetime.timedelta(hours=9)

top_articles = feed.entries[:MAX_ARTICLES]

for article in top_articles:
    title = article.title
    link = article.link # 💡 원문 링크 가져오기
    
    # 💡 2. 기사의 실제 발행일을 파악하여 (M/D) 형태로 변환
    if hasattr(article, 'published_parsed'):
        pub_dt = datetime.datetime.fromtimestamp(time.mktime(article.published_parsed), datetime.timezone.utc)
        if (now_utc - pub_dt).total_seconds() > 24 * 3600:
            continue
        
        pub_kst = pub_dt + datetime.timedelta(hours=9)
        article_date = f"{pub_kst.month}/{pub_kst.day}"
    else:
        article_date = f"{now_kst.month}/{now_kst.day}" # 날짜 정보가 없으면 오늘 날짜로 대체

    print(f"\n🔍 분석 중: {title}")
    
    # [프롬프트 튜닝] 추출한 기사 발행일(article_date)을 제목 양식에 적용
    prompt = f"""
    당신은 금융, 부동산, 통신 산업 전문 수석 애널리스트입니다. 
    사용자가 직접 작성하던 최고 수준의 '뉴스 클리핑 양식'을 완벽하게 모방하여 기사를 요약해야 합니다.
    
    [기사 제목]: {title}

    [작성 양식 및 규칙] - 반드시 아래 형식을 100% 똑같이 지키세요.

    📌 [카테고리명]
    *통찰력 있는 기사 제목 ({article_date})*
    • 핵심단어: 사건의 핵심 내용 기술 → 파급효과나 향후 전망
    • 핵심단어: 주요 기업 동향이나 구체적인 데이터 기술 → 결과
    • 핵심단어: 시장 영향이나 소비자 변화 기술 → 결과

    [세부 지침]
    1. 카테고리: '대출, 부동산, 계좌, 카드, 보험, 자동차, 모바일, 업권' 중 기사와 가장 알맞은 1개를 선택해 대괄호 안에 넣으세요.
    2. 제목: 전체를 아우르는 통찰력 있는 제목을 짓고, 끝에 기사 발행일({article_date})을 넣은 뒤, 전체를 단일 별표(*)로 감싸 굵은 글씨로 만드세요.
    3. 불릿(•) 시작: 각 문장의 시작은 '정책방향:', '시장반응:', '공급실적:' 처럼 2~4글자의 [핵심단어:] 로 문을 여세요.
    4. 🌟강조(가장 중요)🌟: 본문 내용 중 '중요한 주체(기업명, 기관명, 은행명 등)'나 '핵심 숫자(금액, 금리, 비율, 건수 등)'의 양끝에는 반드시 단일 별표(*)를 붙여 시각적으로 강조하세요.
    5. 화살표(→): 원인과 결과, 흐름을 나타낼 때 화살표를 적극 사용하세요.
    6. 기호 주의: 슬랙 굵은 글씨용 단일 별표(*), 불릿(•), 화살표(→) 외에 다른 마크다운 기호(#, **, -, 등)나 출처 링크는 제미나이가 직접 출력하지 마세요.
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
    
    if not summary:
        summary = "(분석 실패)"

    # 💡 3. 요약 내용 밑에 검증용 원문 링크를 직접 추가
    final_message += f"{summary}\n🔗 원문 링크: {link}\n\n\n"
    summarized_count += 1
    
    # 2개를 처리해야 하므로, 첫 번째 기사 요약 후 구글 서버 쿨다운을 위해 10초 대기
    if summarized_count < MAX_ARTICLES:
        time.sleep(10)

if summarized_count == 0:
    final_message = "🤖 현재 24시간 이내의 새로운 산업/금융 뉴스가 없습니다."

if now_kst.hour == 8:
    target_kst = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    wait_seconds = (target_kst - now_kst).total_seconds()
    time.sleep(wait_seconds)

print("\n🚀 슬랙 전송 시작...")
slack_data = {"text": final_message}
res = requests.post(slack_url, headers={"Content-Type": "application/json"}, data=json.dumps(slack_data))

if res.status_code == 200:
    print("✅ 슬랙 전송 완료!")
