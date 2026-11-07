"""Category bubble plot using direct conversions, consistent with category tab."""
import pandas as pd
import plotly.express as px
import streamlit as st
from analysis.category_dashboard import conversion_views,ranking
from analysis.retention_service import retention_events
from analysis.table_styles import heatmap_table
from analysis.data_files import processed_file

UNKNOWN='__UNKNOWN__'


def scatter_data(events,start,end):
    selected=events.loc[events.date.between(pd.Timestamp(start),pd.Timestamp(end))]
    views=conversion_views(selected)
    unknown=int((views.categoryid.isna()|views.categoryid.eq(UNKNOWN)).sum())
    views=views.loc[views.categoryid.notna()&views.categoryid.ne(UNKNOWN)]
    table=ranking(views,'categoryid').drop(columns='순위')
    mapping=views.groupby('categoryid',observed=True).root_categoryid.agg(
        lambda values: sorted(set(values.dropna())-{UNKNOWN}))
    def root_label(values):
        if len(values)==1: return values[0]
        return '복수 대분류' if len(values)>1 else '미확인'
    table['대분류']=table.categoryid.map(mapping.map(root_label))
    table['카테고리']='카테고리 '+table.categoryid.astype(str)
    roots=sorted(set(events.root_categoryid.dropna())-{UNKNOWN})
    palette=px.colors.qualitative.Alphabet+px.colors.qualitative.Dark24
    colors={value:palette[i%len(palette)] for i,value in enumerate(roots)}
    colors.update({'미확인':'#94a3b8','복수 대분류':'#64748b'})
    return table,unknown,colors


def bubble_figure(table,colors,reference=True):
    fig=px.scatter(table,x='장바구니 전환율(%)',y='구매 전환율(%)',
        size='첫 조회 방문자 수',size_max=66,color='대분류',color_discrete_map=colors,
        hover_name='카테고리',hover_data={'categoryid':False,'첫 조회 방문자 수':':,',
            '장바구니 전환 방문자 수':':,','구매 전환 방문자 수':':,',
            '장바구니 전환율(%)':':.2f','구매 전환율(%)':':.2f'},
        labels={'첫 조회 방문자 수':'첫 조회 방문자 수(명)'})
    fig.update_traces(marker={'opacity':.72,'line':{'width':.8,'color':'white'},'sizemode':'area'})
    fig.update_layout(height=650,margin={'l':35,'r':35,'t':35,'b':45},
        paper_bgcolor='white',plot_bgcolor='white',font={'size':15,'color':'#334155'},
        legend={'title':'대분류 ID · 클릭하여 필터','itemsizing':'constant'},
        xaxis={'title':'장바구니 전환율 (%)','ticksuffix':'%','rangemode':'tozero','gridcolor':'#e2e8f0'},
        yaxis={'title':'구매 전환율 (%)','ticksuffix':'%','rangemode':'tozero','gridcolor':'#e2e8f0'})
    if reference and not table.empty:
        fig.add_vline(x=table['장바구니 전환율(%)'].median(),line_dash='dot',line_color='#94a3b8')
        fig.add_hline(y=table['구매 전환율(%)'].median(),line_dash='dot',line_color='#94a3b8')
    return fig


def render_category_scatter(root,start,end):
    st.subheader('카테고리별 전환 성과 산포도')
    st.caption('점 하나는 카테고리 1개 · X축 장바구니 전환율 · Y축 구매 전환율 · 풍선 면적은 첫 조회 방문자 수 · 같은 대분류는 같은 색')
    path=processed_file(root,'events_with_category.csv')
    if not path.exists():
        st.info('카테고리가 연결된 이벤트 파일이 없습니다.')
        return
    version=(path.stat().st_mtime_ns,path.stat().st_size)
    @st.cache_resource(max_entries=3,show_spinner='카테고리별 산포도를 집계하는 중입니다…')
    def cached(path_string,version,start,end):
        return scatter_data(retention_events(path_string,version),start,end)
    original,unknown,colors=cached(str(path),version,start,end)
    if original.empty:
        st.info('선택 기간에 카테고리가 확인된 조회 기록이 없습니다.')
        return
    left,right=st.columns(2)
    minimum=left.number_input('산포도 최소 첫 조회 방문자',min_value=1,value=1,step=100,key='scatter_minimum')
    options=['전체']+sorted(original['대분류'].unique())
    if st.session_state.get('scatter_root') not in options: st.session_state['scatter_root']='전체'
    chosen=right.selectbox('산포도 대분류 필터',options,key='scatter_root')
    table=original.loc[original['첫 조회 방문자 수']>=minimum]
    if chosen!='전체': table=table.loc[table['대분류']==chosen]
    reference=st.checkbox('카테고리 중앙값 기준선 표시',value=True,key='scatter_reference')
    if table.empty:
        st.info('필터 조건에 맞는 카테고리가 없습니다.')
        return
    st.plotly_chart(bubble_figure(table,colors,reference),width='stretch',key='category_bubble_chart',config={'displaylogo':False})
    st.caption(f'표시 {len(table):,}개 / 전체 {len(original):,}개 카테고리 · 미확인 카테고리 조회 {unknown:,}건 제외 · 점선은 현재 표시된 카테고리의 비가중 중앙값')
    st.markdown('**읽는 법:** 오른쪽 위는 두 전환율이 모두 높은 분류입니다. 큰 풍선이 오른쪽 아래에 있으면 장바구니 이후 구매를 추가로 점검할 후보입니다. 소표본의 높은 비율은 과대 해석하지 마세요.')
    st.caption('두 전환율의 분모는 각각 해당 카테고리의 첫 조회 방문자 수입니다. 같은 상품 조회 이후의 행동을 선택 기간 안에서 연결하며, 구매는 장바구니 경유·24시간 제한을 요구하지 않습니다. 첫 조회 수는 반복 이벤트 수가 아닌 고유 방문자 수입니다.')
    with st.expander('산포도 데이터와 다운로드'):
        columns=['categoryid','대분류','첫 조회 방문자 수','장바구니 전환율(%)','구매 전환율(%)','장바구니 전환 방문자 수','구매 전환 방문자 수']
        heatmap_table(table[columns],hide_index=True,width='stretch',column_config={
            name:st.column_config.NumberColumn(format='%.2f%%') for name in columns if name.endswith('(%)')})
        st.download_button('산포도 CSV 다운로드',table[columns].to_csv(index=False).encode('utf-8-sig'),
            f'category_scatter_{start}_{end}.csv','text/csv',key='scatter_download')
