"""Overall / hierarchical 24h funnel and transition distributions."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analysis.funnel_metrics import (prepare, summary, representative, distribution,
                                     UNKNOWN, RATE_COLS)
from analysis.table_styles import heatmap_table
from analysis.data_files import processed_file


def funnel_figure(row,title):
    values = [int(row[c]) for c in ['조회 방문자','장바구니 방문자','구매 방문자']]
    texts = [f'{values[0]:,}명 · 시작 단계']
    for i in (1,2):
        rate = f'{values[i]/values[i-1]*100:.2f}%' if values[i-1] else '—'
        texts.append(f'{values[i]:,}명 · 직전 단계 {rate}')
    fig=go.Figure(go.Funnel(y=['View','AddToCart','Transaction'], x=values,
        text=texts,textinfo='text',textposition='outside',
        marker={'color':['#2563eb','#0891b2','#0d9488']},
        connector={'line':{'color':'#cbd5e1','width':1},'fillcolor':'#e2e8f0'},
        hovertemplate='%{y}<br>%{text}<extra></extra>'))
    fig.update_layout(title={'text':title,'font':{'size':22}},height=430,
        margin={'l':20,'r':230,'t':70,'b':35},paper_bgcolor='white',plot_bgcolor='white',
        font={'size':15,'color':'#334155'},showlegend=False,
        xaxis={'visible':False},yaxis={'tickfont':{'size':16}})
    return fig


def render_funnel_tab(root,start,end):
    st.subheader('24시간 구매 퍼널')
    st.caption('View → AddToCart → Transaction · 같은 방문자·같은 상품 · 첫 관측 조회부터 24시간 이내 · 단계별 고유 방문자')
    path=processed_file(root,'events_with_category.csv')
    if not path.exists():
        st.info('카테고리가 연결된 이벤트 파일이 없습니다.')
        return
    version=(path.stat().st_mtime_ns,path.stat().st_size)

    @st.cache_resource(max_entries=2,show_spinner='24시간 퍼널과 전환 경로를 계산하는 중입니다…')
    def cached_paths(path_string,version,start,end):
        paths=prepare(path_string,start,end)
        return paths,summary(paths),summary(paths,'root_categoryid'),summary(paths,'categoryid')

    paths,total,roots,categories=cached_paths(str(path),version,start,end)
    if paths.empty:
        st.info('선택 기간에 조회 기록이 없습니다.')
        return
    rates={col:st.column_config.NumberColumn(col,format='%.2f%%') for col in RATE_COLS}
    def display_table(table):
        display=table.copy()
        for c in ['root_categoryid','categoryid']:
            if c in display: display[c]=display[c].replace(UNKNOWN,'미확인')
        heatmap_table(display,hide_index=True,width='stretch',column_config=rates)

    def show_scope(scope,title,key):
        row=summary(scope).iloc[0]
        st.plotly_chart(funnel_figure(row,title),width='stretch',key=key,config={'displaylogo':False})
        rate=row['조회→구매(%)']
        st.markdown(f'**조회 → 구매 전체 전환율 {rate:.2f}%**')
        return row

    st.info('24시간은 조회부터 구매까지의 전체 기한입니다. 선택 기간 이후 행동은 포함하지 않으므로 마지막 24시간의 조회자는 추적 시간이 부족할 수 있습니다.')
    st.markdown('### 전체 퍼널')
    row=total.iloc[0]
    a,b,c=st.columns(3)
    for column,name in zip((a,b,c),RATE_COLS):
        value=row[name]
        column.metric(name,f'{value:.2f}%' if pd.notna(value) else '—')
    show_scope(paths,'전체 · 24시간 이내','funnel_overall')
    display_table(total)

    st.markdown('### 대분류·카테고리별 퍼널')
    root_options=roots.root_categoryid.tolist()
    fmt=lambda x:'미확인' if x==UNKNOWN else f'ID {x}'
    if st.session_state.get('funnel_root') not in root_options:
        st.session_state['funnel_root']=root_options[0]
    selected_root=st.selectbox('퍼널 대분류 선택',root_options,format_func=fmt,key='funnel_root')
    root_paths=paths.loc[paths.root_categoryid==selected_root]
    child_table=summary(root_paths,'categoryid')
    options=child_table.categoryid.tolist()
    if st.session_state.get('funnel_category') not in options:
        st.session_state['funnel_category']=options[0]
    selected_category=st.selectbox('퍼널 카테고리 선택',options,format_func=fmt,key='funnel_category')
    category_paths=root_paths.loc[root_paths.categoryid==selected_category]
    left,right=st.columns(2)
    with left:
        show_scope(root_paths,f'대분류 {fmt(selected_root)}','funnel_root_chart')
    with right:
        show_scope(category_paths,f'카테고리 {fmt(selected_category)}','funnel_category_chart')
    with st.expander('선택 분류의 정확한 단계별 수치'):
        display_table(summary(root_paths))
        display_table(summary(category_paths))

    st.divider()
    st.markdown('### 전환 시간과 이전 단계 반복 횟수')
    scope_name=st.radio('분포를 살펴볼 범위',['전체','선택 대분류','선택 카테고리'],horizontal=True,key='funnel_distribution_scope')
    scope={'전체':paths,'선택 대분류':root_paths,'선택 카테고리':category_paths}[scope_name]
    cart=representative(scope,'cart')
    purchase=representative(scope,'purchase')
    st.caption('각 분포는 해당 단계를 통과한 방문자만 포함합니다. 여러 상품에서 전환한 방문자는 이 범위에서 가장 먼저 완료한 동일 상품 경로 1개로 집계합니다. 이탈자의 소요 시간을 뜻하지 않습니다.')

    def bar(rows,column,kind,title,color,key):
        table=distribution(rows,column,kind)
        fig=go.Figure(go.Bar(x=table['구간'],y=table['방문자 수'],marker_color=color,
            text=[f'{v:,}' if v else '' for v in table['방문자 수']],textposition='outside',
            hovertemplate='%{x}<br>%{y:,}명<extra></extra>',cliponaxis=False))
        fig.update_layout(title={'text':title,'font':{'size':19}},height=370,
            margin={'l':20,'r':20,'t':75,'b':90},paper_bgcolor='white',plot_bgcolor='white',
            font={'size':13,'color':'#334155'},yaxis={'title':'방문자 수','rangemode':'tozero','gridcolor':'#e2e8f0'},
            xaxis={'tickangle':-35,'type':'category'})
        st.plotly_chart(fig,width='stretch',key=key,config={'displaylogo':False})
        values=rows[column].dropna().astype(float)
        if len(values):
            unit='분' if kind=='time' else '회'
            st.caption(f'대상 {len(values):,}명 · 중앙값 {values.median():.2f}{unit} · 90백분위 {values.quantile(.9):.2f}{unit}')
        else: st.caption('해당 전환을 완료한 방문자가 없습니다.')
        return table

    time_tables=[]
    for column,(rows,field,label,color) in zip(st.columns(3),[
        (cart,'view_to_cart_min','조회 → 장바구니 소요 시간','#2563eb'),
        (purchase,'cart_to_purchase_min','장바구니 → 구매 소요 시간','#0891b2'),
        (purchase,'view_to_purchase_min','조회 → 구매 전체 소요 시간','#0d9488')]):
        with column:
            table=bar(rows,field,'time',label,color,'funnel_'+field)
            time_tables.append(table.assign(전환=label))
    st.markdown('#### 다음 단계로 넘어가기 전, 이전 행동을 몇 번 했을까요?')
    count_tables=[]
    for column,(rows,field,label,color) in zip(st.columns(2),[
        (cart,'views_before_cart','장바구니에 담기 전 같은 상품 조회 횟수','#2563eb'),
        (purchase,'carts_before_purchase','구매 전 같은 상품 장바구니 추가 횟수','#0891b2')]):
        with column:
            table=bar(rows,field,'count',label,color,'funnel_'+field)
            count_tables.append(table.assign(이전행동=label))
    st.caption('조회 횟수는 첫 조회부터 첫 유효 장바구니 직전까지, 장바구니 횟수는 첫 유효 장바구니부터 첫 유효 구매 직전까지 셉니다. 전환 방문자의 같은 상품 경로 기준이며, 각 행동이 발생한 이벤트 수입니다.')
    with st.expander('분포 집계표 다운로드'):
        st.download_button('소요 시간 분포 CSV',pd.concat(time_tables).to_csv(index=False).encode('utf-8-sig'),f'funnel_times_{start}_{end}.csv','text/csv',key='funnel_times_csv')
        st.download_button('이전 행동 횟수 분포 CSV',pd.concat(count_tables).to_csv(index=False).encode('utf-8-sig'),f'funnel_repetitions_{start}_{end}.csv','text/csv',key='funnel_counts_csv')

    st.divider()
    st.markdown('### 분류별 성과 비교')
    level=st.radio('비교 단위',['대분류','카테고리'],horizontal=True,key='funnel_comparison_level')
    table=roots if level=='대분류' else categories
    include_unknown=st.checkbox('미확인 분류 포함',value=False,key='funnel_include_unknown')
    group_key='root_categoryid' if level=='대분류' else 'categoryid'
    minimum=st.number_input('최소 조회 방문자 수',min_value=0,value=1000,step=100,key='funnel_min_viewers')
    sort=st.selectbox('성과 정렬 기준',['구매 방문자']+RATE_COLS+['조회 방문자'],key='funnel_sort')
    eligible=table.loc[table['조회 방문자']>=minimum]
    if not include_unknown: eligible=eligible.loc[eligible[group_key]!=UNKNOWN]
    eligible=eligible.sort_values(sort,ascending=False,kind='stable')
    st.caption('표본이 작은 분류의 높은 전환율은 불안정할 수 있습니다. 장바구니 → 구매 비율을 비교할 때는 장바구니 방문자 수도 확인하세요. 방문자는 여러 분류에 중복 포함될 수 있습니다.')
    display_table(eligible)
    st.download_button('전체 분류별 퍼널 성과 CSV',table.to_csv(index=False).encode('utf-8-sig'),f'funnel_{level}_{start}_{end}.csv','text/csv',key='funnel_comparison_csv')
    with st.expander('퍼널 집계 및 분류 귀속 기준'):
        st.markdown('''
- 동일 방문자·동일 상품의 선택 기간 내 첫 조회를 시작점으로 합니다. 이후 조회가 있어도 24시간 기한을 다시 시작하지 않습니다.
- 첫 조회 뒤 첫 유효 장바구니, 그 뒤 첫 유효 구매를 연결합니다. 모든 단계의 시각은 엄격히 증가하며 정확히 24시간은 포함합니다.
- 각 단계는 앞 단계를 완료한 고유 방문자만 포함합니다. 구매 전환율은 조회 대비 전체 전환율과 장바구니 대비 단계 전환율을 구분합니다.
- 대분류·카테고리는 상품의 첫 조회 당시 값에 귀속합니다. 그때 분류가 미확인이면 이후 분류로 채우지 않습니다.
- 이 때문에 반복 조회까지 분류별로 세는 첫 조회 성과 탭과 분류별 분모가 다를 수 있습니다.
- 기간 종료 직전 조회자의 추적 부족과 관측 시작 이전 이력 미확인을 고려해야 합니다. 초기 4주도 포함합니다.
''')
