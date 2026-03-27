import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser
from datetime import datetime, timedelta, date
import urllib.parse
import uuid
import json
import os

# 1. 페이지 설정
st.set_page_config(page_title="Global Macro Master v18.1", layout="wide", initial_sidebar_state="expanded")

# --- 방문자 영구 추적 로직 (JSON 파일 저장 방식) ---
VISITOR_FILE = "visitor_stats.json"

def load_visitor_data():
    if os.path.exists(VISITOR_FILE):
        with open(VISITOR_FILE, "r") as f:
            return json.load(f)
    return {}

def save_visitor_data(data):
    with open(VISITOR_FILE, "w") as f:
        json.dump(data, f)

# 현재 동시 접속자(활성 사용자)는 메모리에서만 관리
@st.cache_resource
def get_active_users():
    return {}

active_users = get_active_users()

# 사용자 고유 세션 ID 발급 및 방문자 카운트 누적
if 'session_id' not in st.session_state:
    st.session_state['session_id'] = str(uuid.uuid4())
    today_str = str(date.today())
    
    # 파일에서 기존 데이터 불러오기
    stats = load_visitor_data()
    
    # 오늘 날짜 방문자 1 증가
    stats[today_str] = stats.get(today_str, 0) + 1
    
    # 파일에 다시 저장
    save_visitor_data(stats)

# 현재 사용자의 마지막 활동 시간 업데이트
active_users[st.session_state['session_id']] = datetime.now()

# 5분 이상 활동이 없는 사용자는 '지금 접속자'에서 제외
current_time = datetime.now()
active_sessions = 0
for sid, last_seen in list(active_users.items()):
    if (current_time - last_seen).total_seconds() > 300: # 300초 = 5분
        del active_users[sid]
    else:
        active_sessions += 1

# 통계 표시를 위해 데이터 불러오기
current_stats = load_visitor_data()
today_visitors = current_stats.get(str(date.today()), 0)
total_visitors = sum(current_stats.values())
# ------------------------------------------

# 2. 통합 섹터 데이터베이스
SECTOR_DB = {
    # --- 에너지 ---
    "원유": {"query": '("원유" OR "국제유가" OR "WTI" OR "crude oil") (가동중단 OR 감산 OR OPEC OR 재고)', "keywords": ["원유", "유가", "석유"], "companies": ["SK이노베이션", "S-Oil", "GS", "흥구석유", "중앙에너비스", "극동유화", "한국쉘석유", "미창석유", "대성산업", "지에스이", "대성에너지", "SH에너지화학"]},
    "LNG": {"query": '("LNG" OR "천연가스" OR "Natural Gas") ("파업" OR "가동중단" OR "재고")', "keywords": ["lng", "가스"], "companies": ["한국가스공사", "SK가스", "E1", "삼성중공업", "HD현대중공업", "한화오션", "지역난방공사", "대성에너지", "지에스이", "서울가스", "삼천리", "인천도시가스"]},
    "석탄": {"query": '("석탄" OR "유연탄" OR "Coal") (가격 OR 공급망 OR 발전소 OR 수입)', "keywords": ["석탄", "coal"], "companies": ["LX인터내셔널", "GS글로벌", "포스코인터내셔널", "팬오션", "KCTC", "대한해운", "한전KPS", "한국전력", "케이티앤지", "백광산업", "세아베스틸지주", "STX"]},
    "우라늄": {"query": '("우라늄" OR "Uranium") (가격 OR 원전 OR SMR OR 광산)', "keywords": ["우라늄", "uranium", "원전"], "companies": ["두산에너빌리티", "한전기술", "일진파워", "에너토크", "우진", "보성파워텍", "비에이치아이", "우리기술", "한전KPS", "오르비텍", "한신기계", "지투파워"]},
    
    # --- 기초/산업 비철금속 ---
    "구리(동)": {"query": '("구리 가격" OR "구리값" OR "Copper" OR "전기동") (LME OR 재고 OR 광산 OR 제련) -"구리시" -"동구"', "keywords": ["구리", "copper", "동"], "companies": ["LS", "풍산", "이구산업", "대창", "서원", "KBI메탈", "국일신동", "LS에코에너지", "대한전선", "일진전기", "가온전선", "대원전선"]},
    "알루미늄": {"query": '("알루미늄" OR "Aluminum") (LME OR 재고 OR 제련 OR 가격)', "keywords": ["알루미늄", "aluminum"], "companies": ["조일알미늄", "삼아알미늄", "알루코", "남선알미늄", "피제이메탈", "DI동일", "대호에이엘", "삼보모터스", "동원시스템즈", "율촌화학", "그린플러스", "포스코스틸리온"]},
    "니켈": {"query": '("니켈" OR "Nickel") (LME OR 인도네시아 OR 공급 OR 가격)', "keywords": ["니켈", "nickel"], "companies": ["포스코홀딩스", "LG에너지솔루션", "에코프로비엠", "포스코인터내셔널", "STX", "현대비앤지스틸", "황금에스티", "티플랙스", "율호", "다이나믹디자인", "이엔플러스", "제이스코홀딩스"]},
    "아연/연(납)": {"query": '("아연" OR "Zinc" OR "납 가격" OR "Lead") (LME OR 제련 OR 재고 OR 비철금속)', "keywords": ["아연", "zinc", "납", "lead"], "companies": ["고려아연", "영풍", "한일화학", "풍산", "동국제강", "세아제강", "KG스틸", "디씨엠", "황금에스티", "포스코스틸리온", "대동스틸", "NI스틸"]},
    "주석": {"query": '("주석 가격" OR "Tin") (LME OR 미얀마 OR 인도네시아 OR 반도체 OR 공급)', "keywords": ["주석", "tin"], "companies": ["고려아연", "TCC스틸", "알엔투테크놀로지", "엠케이전자", "덕산하이메탈", "한솔케미칼", "천보", "ISC", "솔브레인", "동진쎄미켐", "이엔에프테크놀로지", "레이크머티리얼즈"]},
    "철광석": {"query": '("철광석" OR "Iron Ore") (중국 OR 철강 OR 제철 OR 재고 OR 감산)', "keywords": ["철광석", "철강"], "companies": ["POSCO홀딩스", "현대제철", "동국제강", "세아제강", "대한제강", "KG스틸", "팬오션", "휴스틸", "하이스틸", "문배철강", "한국주철관", "동국산업"]},
    
    # --- 배터리 및 첨단/희소 광물 ---
    "리튬": {"query": '("리튬" OR "Lithium") (가격 OR 쇼티지 OR 과잉공급 OR 염호)', "keywords": ["리튬", "배터리"], "companies": ["포스코홀딩스", "에코프로", "포스코퓨처엠", "금양", "강원에너지", "하이드로리튬", "리튬포어스", "미래나노텍", "이브이첨단소재", "성일하이텍", "새빗켐", "코스모화학"]},
    "코발트": {"query": '("코발트" OR "Cobalt") (가격 OR 콩고 OR 배터리 OR 공급망)', "keywords": ["코발트", "cobalt"], "companies": ["LG화학", "에코프로비엠", "포스코퓨처엠", "엘앤에프", "코스모화학", "에코프로", "성일하이텍", "새빗켐", "아이에스동서", "DS단석", "고려아연", "영풍"]},
    "망간": {"query": '("망간" OR "Manganese") (가격 OR 배터리 OR 광산 OR 합금)', "keywords": ["망간", "manganese"], "companies": ["에코프로비엠", "엘앤에프", "포스코퓨처엠", "태경산업", "SIMPAC", "동일산업", "나노신소재", "대정화금", "포스코홀딩스", "에코프로", "코스모신소재", "엘앤에프"]},
    "흑연": {"query": '("흑연" OR "Graphite") (가격 OR 중국 OR 수출통제 OR 음극재)', "keywords": ["흑연", "graphite", "음극재"], "companies": ["포스코퓨처엠", "상보", "크리스탈신소재", "태경비케이", "다산솔루에타", "엑사이엔씨", "시노펙스", "이엔플러스", "대주전자재료", "나노신소재", "제이오", "동진쎄미켐"]},
    "텅스텐": {"query": '("텅스텐" OR "Tungsten") (가격 OR 희토류 OR 수출통제 OR 광산)', "keywords": ["텅스텐", "tungsten", "희토류"], "companies": ["상보", "티플랙스", "혜인", "한울소재과학", "유니온", "유니온머티리얼", "동국알앤에스", "노바텍", "쎄노텍", "그린리소스", "영풍정밀", "삼화전자"]},
    
    # --- 귀금속 ---
    "금/은": {"query": '("금값" OR "국제 금" OR "Gold" OR "은값" OR "국제 은" OR "Silver") (안전자산 OR 금리 OR 연준 OR 최고치)', "keywords": ["금", "은", "gold"], "companies": ["고려아연", "엘컴텍", "아이티센", "컴퍼니케이", "정산애강", "비에이치", "엠케이전자", "영풍", "티케이케미칼", "풍산", "LS", "대창"]},
    "백금": {"query": '("백금 가격" OR "Platinum") (촉매 OR 수소 OR 귀금속)', "keywords": ["백금", "platinum"], "companies": ["고려아연", "현대차", "두산퓨얼셀", "프로텍", "동아화성", "일진하이솔루스", "코오롱인더", "평화산업", "평화홀딩스", "상아프론테크", "비나텍", "에스퓨얼셀"]},
    
    # --- 주요 곡물 및 소프트 ---
    "소맥(밀)": {"query": '("밀 가격" OR "국제 밀" OR "소맥" OR "Wheat") (작황 OR 가뭄 OR 수출 OR 선물)', "keywords": ["밀", "소맥", "wheat"], "companies": ["CJ제일제당", "대한제분", "사조동아원", "한탑", "미래생명자원", "팜스토리", "한일사료", "고려산업", "삼양사", "빙그레", "롯데웰푸드", "삼양식품"]},
    "대두(콩)": {"query": '("대두 가격" OR "국제 대두" OR "Soybean") (작황 OR 남미 OR 수출 OR 팜유)', "keywords": ["대두", "콩", "soybean"], "companies": ["CJ제일제당", "풀무원", "대상", "사조대림", "샘표", "신송홀딩스", "미래생명자원", "우성", "샘표식품", "사조해표", "동원F&B", "롯데웰푸드"]},
    "옥수수": {"query": '("옥수수 가격" OR "국제 옥수수" OR "Corn") (작황 OR 에탄올 OR 사료)', "keywords": ["옥수수", "corn"], "companies": ["대상", "팜스토리", "미래생명자원", "사조동아원", "우성", "효성오앤비", "남해화학", "조비", "누보", "경농", "아세아텍", "대동"]},
    "귀리/현미": {"query": '("귀리 가격" OR "Oats" OR "쌀 가격" OR "현미") (가뭄 OR 인도 OR 수출통제 OR 작황)', "keywords": ["귀리", "현미", "쌀"], "companies": ["CJ제일제당", "농심", "오뚜기", "동원F&B", "삼양식품", "풀무원", "빙그레", "크라운해태홀딩스", "농우바이오", "아시아종묘", "대동", "TYM"]},
    "설탕(원당)": {"query": '("설탕 가격" OR "국제 설탕" OR "Sugar" OR "원당") (작황 OR 브라질 OR 가뭄)', "keywords": ["설탕", "sugar"], "companies": ["CJ제일제당", "대상", "대한제당", "삼양사", "보해양조", "창해에탄올", "풍국주정", "무학", "한국알콜", "MH에탄올", "진로발효", "하이트진로"]},
    "커피/코코아": {"query": '("커피 원두" OR "Coffee" OR "코코아" OR "카카오") (작황 OR 가격 OR 가뭄 OR 질병)', "keywords": ["커피", "코코아"], "companies": ["동서", "롯데웰푸드", "해태제과식품", "한국맥널티", "크라운제과", "빙그레", "매일유업", "남양유업", "보라티알", "흥국에프엔비", "크라운해태홀딩스", "삼양식품"]},
    "원목(목재)": {"query": '("원목 가격" OR "국제 목재" OR "Lumber") (주택 OR 건설 OR 산불 OR 선물)', "keywords": ["원목", "목재"], "companies": ["동화기업", "이건산업", "KCC", "한샘", "한솔홈데코", "성창기업지주", "유니드", "대성파인텍", "현대리바트", "LX하우시스", "에넥스", "하츠"]},
    "육류(돈육)": {"query": '("돼지고기 가격" OR "돈육" OR "Lean Hogs") (아프리카돼지열병 OR 구제역 OR 사육두수)', "keywords": ["돼지", "돈육"], "companies": ["선진", "하림", "팜스토리", "우리손에프앤지", "마니커", "체리부로", "정다운", "교촌에프앤비", "동우팜투테이블", "마니커에프앤지", "이지홀딩스", "푸드나무"]}
}

TICKER_MAP = {
    "원유": "CL=F", "LNG": "NG=F", "석탄": "MTF=F", "우라늄": "URA",
    "구리(동)": "HG=F", "알루미늄": "ALI=F", "니켈": "JJN", "아연/연(납)": "ZNC=F", "철광석": "TIO=F",
    "리튬": "LIT", "코발트": "KMET", "텅스텐": "REMX", "금/은": "GC=F", "백금": "PL=F",
    "소맥(밀)": "ZW=F", "대두(콩)": "ZS=F", "옥수수": "ZC=F", "귀리/현미": "ZO=F",
    "설탕(원당)": "SB=F", "커피/코코아": "KC=F", "원목(목재)": "LBS=F", "육류(돈육)": "HE=F"
}

# 3. 사이드바 설정
st.sidebar.header("⚙️ Dashboard Navigation")

PERIOD_OPTIONS = ["7일", "15일", "30일", "60일", "90일", "6개월", "1년", "2년", "3년", "5년", "7년", "10년"]
PERIOD_DAYS = {
    "7일": 7, "15일": 15, "30일": 30, "60일": 60, "90일": 90,
    "6개월": 180, "1년": 365, "2년": 730, "3년": 1095, "5년": 1825, "7년": 2555, "10년": 3650
}

time_frame_label = st.sidebar.selectbox("📅 분석 기간 선택", PERIOD_OPTIONS, index=6)
time_frame_days = PERIOD_DAYS[time_frame_label]

st.sidebar.divider()

# 접속자 통계 항목을 맨 끝으로 이동
menu_options = ["🏠 대시보드 홈 (전체)"] + list(SECTOR_DB.keys()) + ["📊 접속자 통계 (트래픽)"]
selected_menu = st.sidebar.radio("📌 집중 분석 섹터 선택", menu_options)

# 사이드바 하단 트래픽 모니터 (JSON 데이터 연동)
st.sidebar.divider()
st.sidebar.subheader("📡 실시간 트래픽 모니터")
col1, col2 = st.sidebar.columns(2)
col1.metric("지금 접속자", f"{active_sessions} 명")
col2.metric("금일 접속자", f"{today_visitors} 명")
st.sidebar.caption(f"누적 총 접속자: {total_visitors} 명")

# 4. 핵심 스크랩 및 분석 로직
def analyze_news(title):
    t = title.lower()
    if any(x in t for x in ["파업", "strike", "중단", "halt", "부족", "shortage", "가뭄", "수출통제", "전염병", "산불", "질병", "감산"]):
        return "🚨", "🔴 강력 호재(공급축소)", "🔥 공급망/작황 악재 발생! 가격 상승 압력이 강합니다."
    elif any(x in t for x in ["수주", "계약", "호조", "최고치", "급등", "폭등", "수요 증가"]):
        return "💡", "🟢 호재(수요/가격상승)", "📈 수요 증가 또는 가격 급등 소식입니다. 긍정적 모멘텀 기대."
    elif any(x in t for x in ["하락", "폭락", "drop", "plunge", "과잉", "안정", "풍작", "재고 증가"]):
        return "📉", "🔵 악재(가격하락)", "❄️ 가격 하향 또는 공급 안정(풍작) 추세입니다. 단기 수익성 악화 주의."
    return "➖", "⚪ 중립", "📊 통상적인 시황 뉴스입니다."

@st.cache_data(ttl=600)
def fetch_news(sector_target="ALL"):
    combined_news = []
    sources = [{"hl": "ko-KR", "gl": "KR", "ceid": "KR:ko"}, {"hl": "en-US", "gl": "US", "ceid": "US:en"}]
    
    sectors_to_fetch = SECTOR_DB if sector_target == "ALL" else {sector_target: SECTOR_DB[sector_target]}
    limit = 3 if sector_target == "ALL" else 10 
    
    for category, info in sectors_to_fetch.items():
        for src in sources:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(info['query'])}&hl={src['hl']}&gl={src['gl']}&ceid={src['ceid']}"
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]: 
                try:
                    dt = datetime(*entry.published_parsed[:6]) + timedelta(hours=9)
                    date_str = dt.strftime("%m.%d %H:%M")
                    real_time = dt 
                except: 
                    date_str = "최근"
                    real_time = datetime.now()
                
                important, status, summary = analyze_news(entry.title)
                
                display_companies = info["companies"][:12]
                if len(info["companies"]) > 12:
                    display_companies.append("등")
                    
                combined_news.append({
                    "_정렬용시간": real_time,
                    "중요도": important,
                    "시간(KST)": date_str,
                    "섹터": category,
                    "뉴스 제목": entry.title,
                    "AI 판단": status,
                    "AI 분석 요약": summary,
                    "관련 국내 기업": ", ".join(display_companies),
                    "링크": entry.link
                })
                
    df = pd.DataFrame(combined_news)
    if not df.empty:
        df = df.drop_duplicates(subset=['뉴스 제목'])
        df = df.sort_values(by="_정렬용시간", ascending=False)
        df = df.drop(columns=['_정렬용시간'])
    return df

def highlight_row(row):
    if row['중요도'] == '🚨': return ['background-color: rgba(255, 100, 100, 0.15)'] * len(row)
    elif row['중요도'] == '💡': return ['background-color: rgba(100, 255, 100, 0.15)'] * len(row)
    elif row['중요도'] == '📉': return ['background-color: rgba(100, 150, 255, 0.15)'] * len(row)
    return [''] * len(row)

def add_moving_averages(data, days):
    try:
        if isinstance(data.columns, pd.MultiIndex):
            close_series = data['Close'].iloc[:, 0]
        else:
            close_series = data['Close']
            
        chart_df = pd.DataFrame({'종가': close_series})
        
        if days <= 30:
            short_ma, long_ma = 5, 10
            label = "일선"
        elif days <= 180:
            short_ma, long_ma = 10, 20
            label = "일선"
        elif days < 1095:
            short_ma, long_ma = 20, 60
            label = "일선"
        else:
            short_ma, long_ma = 10, 40 
            label = "주선"
            
        chart_df[f'{short_ma}{label}'] = chart_df['종가'].rolling(window=short_ma, min_periods=1).mean()
        chart_df[f'{long_ma}{label}'] = chart_df['종가'].rolling(window=long_ma, min_periods=1).mean()
        return chart_df
    except Exception:
        if isinstance(data.columns, pd.MultiIndex):
            return pd.DataFrame({'종가': data['Close'].iloc[:, 0]})
        return pd.DataFrame({'종가': data['Close']})

padded_days = time_frame_days + 300 
padded_start_date = (datetime.now() - timedelta(days=padded_days)).strftime('%Y-%m-%d')
target_start_date = pd.to_datetime((datetime.now() - timedelta(days=time_frame_days)).strftime('%Y-%m-%d'))
chart_interval = "1wk" if time_frame_days >= 1095 else "1d"

# 5. 메인 화면 렌더링 로직
if selected_menu == "🏠 대시보드 홈 (전체)":
    st.title("🌐 Global Macro Master v18.1")
    st.caption(f"선택된 분석 기간: {time_frame_label} | 전체 원자재 섹터 오버뷰 및 추세선")

    chart_groups = {
        "에너지 및 귀금속": {"원유": "CL=F", "LNG": "NG=F", "우라늄(ETF)": "URA", "금": "GC=F"},
        "비철/배터리 금속": {"구리(동)": "HG=F", "알루미늄": "ALI=F", "리튬(ETF)": "LIT", "철광석": "TIO=F"},
        "주요 식량 및 기타": {"소맥(밀)": "ZW=F", "대두(콩)": "ZS=F", "설탕": "SB=F", "원목": "LBS=F"}
    }

    for group_name, commodities in chart_groups.items():
        st.markdown(f"**📌 {group_name} 대표 지수**")
        cols = st.columns(len(commodities))
        for i, (name, ticker) in enumerate(commodities.items()):
            with cols[i]:
                try:
                    data = yf.download(ticker, start=padded_start_date, interval=chart_interval, progress=False)
                    if not data.empty:
                        chart_data_full = add_moving_averages(data, time_frame_days)
                        chart_data_full.index = chart_data_full.index.tz_localize(None)
                        chart_data = chart_data_full[chart_data_full.index >= target_start_date]
                        
                        curr = float(chart_data_full['종가'].iloc[-1])
                        if not chart_data.empty:
                            prev = float(chart_data['종가'].iloc[0])
                            change_pct = ((curr - prev) / prev) * 100
                            st.metric(name, f"${curr:.2f}", f"{change_pct:.2f}%")
                            st.line_chart(chart_data, height=120)
                        else:
                            st.metric(name, f"${curr:.2f}", "0.00%")
                            st.line_chart(chart_data_full.tail(5), height=120)
                    else:
                        st.metric(name, "N/A", "데이터 없음")
                except:
                    st.metric(name, "Error", "로드 실패")
        st.write("") 
    
    st.divider()
    
    if st.button('🔍 전체 원자재 속보 통합 분석 시작'):
        with st.spinner('전 섹터의 최신 뉴스를 스크랩 중입니다. (약 15~20초 소요)...'):
            df = fetch_news(sector_target="ALL")
            if not df.empty:
                styled_df = df.style.apply(highlight_row, axis=1)
                st.dataframe(
                    styled_df,
                    column_config={
                        "관련 국내 기업": st.column_config.TextColumn("관련 기업", width="large"),
                        "링크": st.column_config.LinkColumn("원문", display_text="기사보기 🔗"),
                    },
                    use_container_width=True, height=600, hide_index=True
                )

# --- 접속자 통계 페이지 ---
elif selected_menu == "📊 접속자 통계 (트래픽)":
    st.title("📊 대시보드 접속자 통계")
    st.caption("대시보드 접속 현황을 일간, 주간, 월간 단위로 분석합니다.")
    
    stats_data = load_visitor_data()
    
    if not stats_data:
        st.info("아직 누적된 방문자 데이터가 충분하지 않습니다. (오늘부터 기록이 시작됩니다)")
    else:
        # JSON 데이터를 Pandas DataFrame으로 변환
        df_stats = pd.DataFrame(list(stats_data.items()), columns=['날짜', '접속자 수'])
        df_stats['날짜'] = pd.to_datetime(df_stats['날짜'])
        df_stats = df_stats.set_index('날짜').sort_index()
        
        # 상단 요약 지표
        st.markdown("### 📈 트래픽 요약")
        c1, c2, c3 = st.columns(3)
        c1.metric("총 누적 접속자", f"{int(df_stats['접속자 수'].sum())} 명")
        c2.metric("일일 최고 접속자", f"{int(df_stats['접속자 수'].max())} 명")
        c3.metric("평균 일일 접속자", f"{int(df_stats['접속자 수'].mean())} 명")
        st.divider()
        
        # 보기 단위 선택 라디오 버튼
        view_type = st.radio("보기 단위 선택", ["일간 (Daily)", "주간 (Weekly)", "월간 (Monthly)"], horizontal=True)
        
        # 선택한 단위에 맞춰 Pandas resample(데이터 그룹화) 실행
        if view_type == "일간 (Daily)":
            chart_data = df_stats
            st.markdown("##### 📅 일간 접속자 추이")
        elif view_type == "주간 (Weekly)":
            chart_data = df_stats.resample('W').sum()
            chart_data.index = chart_data.index.strftime('%Y년 %U주차')
            st.markdown("##### 주간 접속자 추이")
        else:
            chart_data = df_stats.resample('ME').sum()
            chart_data.index = chart_data.index.strftime('%Y년 %m월')
            st.markdown("##### 🗓️ 월간 접속자 추이")
            
        # 막대 그래프 렌더링
        st.bar_chart(chart_data['접속자 수'], height=400)
        
        # 데이터프레임 표 형태로도 제공
        with st.expander("📊 상세 데이터 표 보기"):
            st.dataframe(chart_data, use_container_width=True)

# ------------------------------------
else:
    st.title(f"🔍 {selected_menu} 심층 분석")
    st.caption(f"선택된 분석 기간: {time_frame_label} | 좌측 메뉴에서 다른 원자재를 선택하거나 홈으로 돌아갈 수 있습니다.")
    
    ticker = TICKER_MAP.get(selected_menu)
    if ticker:
        try:
            data = yf.download(ticker, start=padded_start_date, interval=chart_interval, progress=False)
            if not data.empty:
                chart_data_full = add_moving_averages(data, time_frame_days)
                chart_data_full.index = chart_data_full.index.tz_localize(None)
                chart_data = chart_data_full[chart_data_full.index >= target_start_date]
                
                curr = float(chart_data_full['종가'].iloc[-1])
                
                if not chart_data.empty:
                    prev = float(chart_data['종가'].iloc[0])
                    change_pct = ((curr - prev) / prev) * 100
                    st.metric(f"{selected_menu} 가격", f"${curr:.2f}", f"{change_pct:.2f}%")
                    st.line_chart(chart_data, height=350, use_container_width=True)
                else:
                    st.metric(f"{selected_menu} 가격", f"${curr:.2f}", "0.00%")
                    st.warning(f"선택하신 기간({time_frame_label}) 내에 발생한 거래 데이터가 없습니다. (최근 거래 내역을 대신 표시합니다.)")
                    st.line_chart(chart_data_full.tail(10), height=350, use_container_width=True)
            else:
                st.info("해당 원자재의 설정된 기간 내 실시간 차트 데이터를 불러올 수 없습니다.")
        except Exception as e:
            st.warning("차트 데이터를 불러오는 중 일시적인 네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
            
    st.divider()
    
    st.subheader(f"📰 {selected_menu} 최신 심층 뉴스 (최대 20건)")
    with st.spinner(f'{selected_menu} 관련 국내외 속보를 수집 중입니다...'):
        df = fetch_news(sector_target=selected_menu)
        if not df.empty:
            styled_df = df.style.apply(highlight_row, axis=1)
            st.dataframe(
                styled_df,
                column_config={
                    "중요도": st.column_config.TextColumn("중요도", width="small"),
                    "시간(KST)": st.column_config.TextColumn("시간", width="small"),
                    "섹터": st.column_config.TextColumn("섹터", width="small", disabled=True),
                    "뉴스 제목": st.column_config.TextColumn("기사 제목", width="large"),
                    "AI 판단": st.column_config.TextColumn("AI 판단", width="medium"),
                    "AI 분석 요약": st.column_config.TextColumn("AI Insight", width="large"),
                    "관련 국내 기업": st.column_config.TextColumn("관련 기업", width="large"),
                    "링크": st.column_config.LinkColumn("원문", display_text="기사보기 🔗"),
                },
                use_container_width=True,
                height=500,
                hide_index=True
            )
        else:
            st.warning(f"최근 이슈 중 {selected_menu} 관련 주요 뉴스가 검색되지 않았습니다.")