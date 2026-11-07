"""Launch from project root: streamlit run analysis/dashboard.py"""
from pathlib import Path
import sys
import streamlit as st
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.dashboard_metrics import METRICS, load_events, summarize
from analysis.category_dashboard import render_category_tab
from analysis.funnel_dashboard import render_funnel_tab
from analysis.table_styles import heatmap_table
from analysis.retention_dashboard import render_retention_tab
from analysis.category_scatter import render_category_scatter
from analysis.data_files import processed_file

st.set_page_config(page_title='구매 전환 · 주요 지표', page_icon='📈', layout='wide')
st.markdown('''<style>
.stApp {background: #f4f7fb; color: #0f172a; color-scheme: light;}
[data-testid="stMetric"] {background: white; padding: 22px 26px; border: 1px solid #dbe3ef; border-top: 4px solid #2563eb; border-radius: 14px; box-shadow: 0 3px 12px #0f172a06;}
[data-testid="stMetricLabel"] p {font-size: 17px !important; color: #334155 !important; font-weight: 650;}
[data-testid="stMetricValue"] {font-size: clamp(1.8rem, 3vw, 2.75rem); font-weight: 750; color: #0f172a; letter-spacing: -1px;}
[data-testid="stCaptionContainer"] p {font-size: 15px; color: #475569;}
h1,h2,h3 {color: #0f172a !important; letter-spacing: -.5px;}
button[data-baseweb="tab"] {font-size: 19px; font-weight: 700; padding: 14px 24px;}
[data-testid="stPlotlyChart"] {border: 1px solid #dbe3ef; border-radius: 14px; overflow: hidden; background: white;}
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1480px;}
</style>''', unsafe_allow_html=True)
st.title('구매 전환 · 주요 지표')
st.caption('사용자 규모부터 구매까지, 선택한 기간의 핵심 성과를 한눈에 확인하세요.')
source = processed_file(ROOT, 'events_clean.csv')
if not source.is_file():
    st.error('정제 이벤트 파일이 없습니다. 먼저 전처리를 실행해 주세요.')
    st.stop()


@st.cache_resource(show_spinner='이벤트 데이터를 불러오는 중입니다…', max_entries=1)
def get_events(version):
    # This shared frame is read-only; filtering/aggregation never mutates it.
    return load_events(source)


@st.cache_data(show_spinner='선택 기간의 지표를 집계하는 중입니다…', max_entries=8)
def get_summary(version, start, end):
    return summarize(get_events(version), start, end)


version = (source.stat().st_mtime_ns, source.stat().st_size)
events = get_events(version)
if events.empty:
    st.info('분석 가능한 이벤트가 없습니다.')
    st.stop()
earliest, latest = events['date'].min().date(), events['date'].max().date()
dates = st.date_input('분석 기간 선택', value=(earliest, latest), min_value=earliest,
                      max_value=latest, format='YYYY/MM/DD')
if not isinstance(dates, (tuple, list)) or len(dates) != 2:
    st.info('캘린더에서 시작일과 종료일을 모두 선택해 주세요.')
    st.stop()
start, end = dates
if start > end:
    st.error('종료일은 시작일 이후여야 합니다.')
    st.stop()
st.caption(f'{start:%Y.%m.%d} — {end:%Y.%m.%d} · {(end-start).days+1}일 · UTC · 양 끝 날짜 포함')
if start == earliest or end == latest:
    st.caption('◐ 부분 관측: 5월 3일은 03:00부터, 9월 15일은 21:00까지입니다. 월간 비교 시 관측 기간을 확인하세요.')

kpis, daily, monthly = get_summary(version, start, end)
st.subheader('선택 기간 핵심 지표')
definitions = {
    '활성 사용자 수': '모든 이벤트 중 1회 이상 수행한 고유 방문자',
    '구매자 수': '구매 이벤트를 1회 이상 수행한 고유 방문자',
    '구매 횟수': '고유 거래 ID 수 · 한 주문의 여러 상품은 1회',
    '장바구니에 담은 횟수': '장바구니 추가 이벤트 건수 · 상품 수량 아님',
    '이벤트 횟수': '조회 + 장바구니 + 구매 이벤트 건수',
}
names = list(METRICS)
for group in (names[:3], names[3:]):
    for column, name in zip(st.columns(len(group)), group):
        unit, _ = METRICS[name]
        column.metric(name, f'{kpis[name]:,}{unit}', help=definitions[name])
        column.caption(definitions[name])
if kpis['활성 사용자 수']:
    ratio = kpis['구매자 수'] / kpis['활성 사용자 수'] * 100
    st.markdown(f'**구매자 비율 {ratio:.2f}%** · 활성 사용자 중 구매 경험이 있는 사용자의 비율입니다. 순차 퍼널 전환율과는 다릅니다.')
if kpis['이벤트 횟수'] == 0:
    st.warning('선택 기간에 이벤트가 없습니다. 지표와 추이를 0으로 표시합니다.')


def show_trends(frame, mode):
    st.subheader(f'{mode} 변화 살펴보기')
    focus = st.selectbox('크게 볼 지표', list(METRICS), index=2, key=f'focus_{mode}')

    def draw_chart(name, large=False):
        unit, color = METRICS[name]
        show_values = mode == '월별' or len(frame) <= 10
        fig = go.Figure(go.Scatter(
            x=frame.index, y=frame[name], mode='lines+markers+text' if show_values else 'lines',
            text=[f'{v:,}' for v in frame[name]] if show_values else None,
            textposition='top center', textfont={'size': 15, 'color': '#0f172a'},
            name=name, line={'color': color, 'width': 3},
            marker={'size': 8}, cliponaxis=False,
            hovertemplate=('%{x|%Y-%m-%d}' if mode == '일별' else '%{x|%Y-%m}') +
                          f'<br>{name}: %{{y:,.0f}}{unit}<extra></extra>'))
        fig.update_layout(title={'text': f'<b>{name}</b>', 'font': {'size': 23 if large else 20}}, height=430 if large else 340,
                          margin={'l': 35, 'r': 40, 't': 75, 'b': 40},
                          paper_bgcolor='white', plot_bgcolor='white',
                          font={'family': 'Arial, Apple SD Gothic Neo, sans-serif', 'size': 15, 'color': '#334155'},
                          hovermode='x unified', showlegend=False)
        fig.update_yaxes(title=unit, rangemode='tozero', tickformat=',', gridcolor='#e2e8f0')
        fig.update_xaxes(tickformat='%m/%d' if mode == '일별' else '%Y-%m',
                         dtick='M1' if mode == '월별' else None, showgrid=False)
        if mode == '월별':
            import pandas as pd
            for stamp in frame.index:
                month_end = stamp + pd.offsets.MonthEnd(0)
                if start > stamp.date() or end < month_end.date() or stamp.date() <= earliest <= month_end.date() or stamp.date() <= latest <= month_end.date():
                    fig.add_vrect(x0=stamp-pd.Timedelta(days=3), x1=stamp+pd.Timedelta(days=3),
                                  fillcolor='#f59e0b', opacity=.1, line_width=0, layer='below')
        st.plotly_chart(fig, width='stretch', key=f'{mode}_{name}',
                        config={'displaylogo': False, 'scrollZoom': False})

    draw_chart(focus, large=True)
    if len(frame) and frame[focus].sum() > 0:
        peak = frame[focus].idxmax()
        label = peak.strftime('%Y-%m-%d' if mode == '일별' else '%Y-%m')
        st.caption(f'선택 범위 내 최대: {label} · {frame.loc[peak, focus]:,}{METRICS[focus][0]} · 마우스를 올리면 각 시점의 정확한 값을 확인할 수 있습니다.')
    st.markdown('#### 나머지 지표 함께 보기')
    remaining = [name for name in METRICS if name != focus]
    for offset in range(0, len(remaining), 2):
        for column, name in zip(st.columns(2), remaining[offset:offset+2]):
            with column:
                draw_chart(name)
    with st.expander(f'{mode} 집계표 보기 및 다운로드'):
        table = frame.copy()
        table.index = table.index.strftime('%Y-%m-%d' if mode == '일별' else '%Y-%m')
        heatmap_table(table, width='stretch')
        st.download_button(f'{mode} CSV 다운로드', table.to_csv().encode('utf-8-sig'),
                           file_name=f'{"daily" if mode == "일별" else "monthly"}_{start}_{end}.csv',
                           mime='text/csv', key=f'download_{mode}')


st.divider()
trend_tab, category_tab, funnel_tab, retention_tab = st.tabs(
    ['주요 지표 추이', '카테고리별 첫 조회 성과', '퍼널 분석','리텐션'],
    key='dashboard_section',on_change='rerun')
# Hidden tabs do not load/aggregate their datasets or render large styled tables.
if trend_tab.open:
    with trend_tab:
        daily_tab, monthly_tab, scatter_tab=st.tabs(['일별 추이','월별 추이','카테고리 산포도'],
            key='trend_section',on_change='rerun')
        if daily_tab.open:
            with daily_tab:
                show_trends(daily, '일별')
        if monthly_tab.open:
            with monthly_tab:
                st.caption('주황색 배경은 일부 기간만 관측한 월입니다. 월별 수치는 선택한 날짜 범위만 포함하며, 고유 사용자 수는 월마다 새로 집계합니다.')
                show_trends(monthly, '월별')
        if scatter_tab.open:
            with scatter_tab:
                render_category_scatter(ROOT,start,end)
if category_tab.open:
    with category_tab:
        render_category_tab(ROOT, start, end)
if funnel_tab.open:
    with funnel_tab:
        render_funnel_tab(ROOT, start, end)
if retention_tab.open:
    with retention_tab:
        render_retention_tab(ROOT,start,end)
with st.expander('집계 기준과 해석 시 주의 사항'):
    st.markdown('''
- 구매자 수는 구매 이벤트를 수행한 고유 방문자, 장바구니 횟수는 추가 이벤트 건수입니다.
- 구매 횟수는 주문 단위입니다. 여러 상품이 포함된 주문은 구매 이벤트가 여러 건이어도 1회입니다.
- 완전 중복 제거 정제본을 사용하며, 초기 4주를 포함합니다. 관측 이전 이력이 없어 첫 관측을 신규 고객으로 단정하지 않습니다.
- 첫날·마지막 날 및 선택 범위의 양 끝 월은 일부 기간만 포함될 수 있습니다. 감소를 곧바로 성과 하락으로 해석하지 마세요.
- 금액 정보가 없으므로 매출 지표는 제공하지 않습니다.
''')
