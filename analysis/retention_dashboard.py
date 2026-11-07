"""Behavior-qualified cohorts: buyer/cart/both comparison and retention curves."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analysis.retention_metrics import SPECS,UNKNOWN,metric_row,retention_curve,retention_columns,GRAINS,observation_days
from analysis.retention_service import retention_events,cached_retention,cached_visit_cohorts
from analysis.table_styles import heatmap_table
from analysis.data_files import processed_file


def render_visit_cohorts(path,version,start,end,key,entity,root,category,grain,cohort_end=None):
    prefix,unit,_=GRAINS[grain]
    st.markdown('### 방문일 기준 리텐션 코호트')
    st.caption('이 표는 조회만 한 사용자도 포함한 전체 방문자 기준입니다. 행은 데이터 내 첫 방문 구간, 분모는 해당 행의 0번째 구간 사용자 수로 고정됩니다. 각 칸은 정확히 N번째 구간의 사용자 수와 재방문율입니다.')
    st.caption(f'대상 방문일: {start} ~ {cohort_end or end} · 이 기간에 첫 방문이 관측된 사용자만 포함하며, 이후 재방문은 전체 분석 종료일까지 추적합니다.')
    data=cached_visit_cohorts(path,version,start,end,key,entity,root,category,grain,cohort_end=cohort_end)
    if data.empty:
        st.info('선택한 범위에 첫 방문 코호트가 없습니다.')
        return
    counts=data.pivot(index='방문 코호트',columns='N',values='재방문 사용자')
    rates=data.pivot(index='방문 코호트',columns='N',values='비율(%)')
    labels=counts.copy().astype(object)
    for n in counts.columns:
        labels[n]=[f'{int(c):,}명 · {r:.2f}%' if pd.notna(c) else '—'
                   for c,r in zip(counts[n],rates[n])]
    labels.columns=[f'{prefix}{n}' for n in labels.columns]
    rates.columns=labels.columns
    ceiling=st.selectbox('코호트 색상 상한',[5,10,100],format_func=lambda v:f'{v}% (이상은 같은 진하기)',key='cohort_color_ceiling')
    def colors(column):
        result=[]
        for value in rates[column.name]:
            if pd.isna(value):
                result.append('background-color: #f1f5f9; color: #64748b')
            else:
                weight=min(value/ceiling,1)
                rgb=tuple(round(a+(b-a)*weight) for a,b in zip((239,246,255),(29,78,216)))
                fg='#ffffff' if weight>=.6 else '#0f172a'
                result.append(f'background-color: rgb{rgb}; color: {fg}')
        return result
    with pd.option_context('styler.render.max_elements',max(262144,labels.size)):
        st.dataframe(labels.style.apply(colors,axis=0),width='stretch',height=620,
                     column_config={c:st.column_config.TextColumn(width='medium') for c in labels},
                     key='retention_visit_cohorts')
    st.caption(f'공통 색상 척도: 0% → {ceiling}% · 진할수록 높은 재방문율 · 회색 —는 미관측, 0명은 관측된 무방문입니다. {prefix}0은 기준 집단이므로 100%입니다. 주별 행 날짜는 월요일, 월별 행은 해당 월을 뜻합니다. 양 끝 코호트의 최초 구간은 일부만 관측되었을 수 있습니다.')
    st.download_button('방문 코호트 전체 CSV',data.to_csv(index=False).encode('utf-8-sig'),
                       f'visit_cohorts_{grain}_{start}_{cohort_end or end}_observed_{end}.csv','text/csv',key='visit_cohorts_download')


def render_retention_tab(root,start,end):
    st.subheader('리텐션 · 장바구니와 구매 이후 다시 돌아왔을까요?')
    st.caption('분석 대상은 선택 종료일까지 장바구니 또는 구매가 관측된 사용자입니다. 재방문은 같은 분류의 모든 이벤트, 재구매는 같은 분류의 구매 이벤트로 판단합니다.')
    path=processed_file(root,'events_with_category.csv')
    if not path.exists():
        st.info('카테고리가 연결된 이벤트 파일이 없습니다.')
        return
    path=str(path)
    from pathlib import Path
    stat=Path(path).stat()
    version=(stat.st_mtime_ns,stat.st_size)
    events=retention_events(path,version)
    if events.empty:
        st.info('리텐션을 계산할 방문 이력이 없습니다.')
        return
    earliest=pd.to_datetime(events.day.min()*86400000,unit='ms').date()
    last_complete=observation_days(start,end)[1]
    latest=pd.to_datetime(last_complete*86400000,unit='ms').date()
    if latest < earliest:
        st.info('선택한 분석 기간에 완전히 관측된 날짜가 없습니다.')
        return
    calendar_key='retention_cohort_dates'
    if calendar_key in st.session_state:
        stored=st.session_state[calendar_key]
        if any(d < earliest or d > latest for d in stored):
            st.session_state[calendar_key]=(max(earliest,min(pd.Timestamp(start).date(),latest)),latest)
    dates=st.date_input('리텐션 코호트 방문 기간',
        value=(max(earliest,min(pd.Timestamp(start).date(),latest)),latest),
        min_value=earliest,max_value=latest,format='YYYY/MM/DD',key=calendar_key,
        help='첫 방문일이 선택 기간에 포함된 사용자만 코호트에 포함합니다. 하루만 분석하려면 시작일과 종료일을 같은 날짜로 선택하세요. 이후 재방문은 전체 분석 종료일까지 추적합니다.')
    if not isinstance(dates,(tuple,list)) or len(dates)!=2:
        st.info('캘린더에서 코호트 방문 시작일과 종료일을 모두 선택해 주세요.')
        return
    start,cohort_end=dates
    st.caption(f'코호트 방문 기간: {start:%Y.%m.%d} ~ {cohort_end:%Y.%m.%d} · 재방문 추적: {latest:%Y.%m.%d}까지 (UTC)')
    grain=st.radio('리텐션 시간 단위',list(GRAINS),horizontal=True,key='retention_grain')
    prefix,unit,horizon=GRAINS[grain]
    window=f'{horizon}{unit}'
    def display_columns(frame):
        return frame.rename(columns=lambda c:c.replace('30일',window))
    def cached(*args,**kwargs):
        return cached_retention(*args,grain=grain,cohort_end=cohort_end,**kwargs)
    level=st.radio('리텐션 분석 단위',['전체','대분류','카테고리','상품'],horizontal=True,key='retention_level')
    fmt=lambda x:'미확인' if x==UNKNOWN else f'ID {x}'
    entity='전체';key=None;selected_root=None;selected_category=None
    if level!='전체':
        root_table=cached(path,version,start,end,'root_categoryid')['stats']
        options=root_table.loc[root_table.metric=='activity_return'].sort_values('코호트 사용자',ascending=False)._entity.tolist()
        if not options:
            st.info('장바구니 또는 구매 사용자 기록이 없습니다.')
            return
        if st.session_state.get('retention_root') not in options: st.session_state['retention_root']=options[0]
        selected_root=st.selectbox('리텐션 대분류 선택',options,format_func=fmt,key='retention_root')
        entity=selected_root;key='root_categoryid'
        if level in ('카테고리','상품'):
            pack=cached(path,version,start,end,'categoryid',root=selected_root)
            options=pack['stats'].loc[pack['stats'].metric=='activity_return'].sort_values('코호트 사용자',ascending=False)._entity.tolist()
            if not options:
                st.info('선택 분류의 행동 사용자 기록이 없습니다.')
                return
            if st.session_state.get('retention_category') not in options: st.session_state['retention_category']=options[0]
            selected_category=st.selectbox('리텐션 카테고리 선택',options,format_func=fmt,key='retention_category')
            entity=selected_category;key='categoryid'
            if level=='상품':
                pack=cached(path,version,start,end,'itemid',root=selected_root,category=selected_category)
                options=pack['stats'].loc[pack['stats'].metric=='activity_return'].sort_values('코호트 사용자',ascending=False)._entity.tolist()
                if not options:
                    st.info('선택 경로에 상품 기록이 없습니다.')
                    return
                if st.session_state.get('retention_item') not in options: st.session_state['retention_item']=options[0]
                entity=st.selectbox('리텐션 상품 선택',options,format_func=fmt,key='retention_item');key='itemid'
    if key is None:
        pack=cached(path,version,start,end)
    elif key=='root_categoryid':
        pack=cached(path,version,start,end,key)
    last_complete=pd.to_datetime(pack['last_complete']*86400000,unit='ms').date()
    st.info(f'{grain} · {window} 지표와 {prefix}1~{prefix}{horizon} 곡선은 마지막 추적 구간까지 완전히 관측한 동일 코호트로 계산합니다. 완전 관측 종료일: {last_complete}. 같은 구간 내 반복 활동은 한 명으로 계산합니다.')
    st.caption('일별은 UTC 날짜, 주별은 월요일~일요일, 월별은 달력 월 기준입니다. 주·월이 끝나지 않은 추적 구간은 미관측으로 처리합니다.')
    render_visit_cohorts(path,version,start,end,key,entity,selected_root,selected_category,grain,cohort_end)
    st.caption('탭의 캘린더는 코호트 기준일의 범위를 선택합니다. 행동별 비교는 각 지표의 최초 행동일을 기준으로 같은 기간을 적용합니다. 페이지 상단 분석 종료일은 후속 행동의 관측 종료일입니다. 선택 기간 이전 이력도 확인하며 첫 방문일을 다시 설정하지 않습니다.')
    mode=st.radio('그래프 방식',['당일','누적'],horizontal=True,key='retention_mode',
        format_func=lambda x:('해당 '+unit if x=='당일' else x),
        help=f'해당 {unit}: 정확히 N번째 구간에 활동. 누적: 1~N번째 구간 중 한 번이라도 복귀. 요약 지표는 {window} 누적입니다.')

    def cards(metrics):
        for column,metric in zip(st.columns(len(metrics)),metrics):
            row=metric_row(pack,entity,metric)
            rate=row['30일 비율(%)']
            column.metric(window+' '+SPECS[metric][0],f'{rate:.2f}%' if pd.notna(rate) else '—')
            column.caption(f"{row['30일 재방문 사용자']:,}명 / {row['30일 관측 가능 사용자']:,}명 · 추적 부족 제외 {row['추적 부족 제외 사용자']:,}명")

    def curves(selected,title,chart_key,source=None,entities=None):
        source=pack if source is None else source
        series=[(entity,metric,SPECS[metric][0]) for metric in selected] if entities is None else entities
        fig=go.Figure()
        colors=['#2563eb','#ea580c','#0d9488','#7c3aed','#0891b2']
        for i,(chosen,metric,label) in enumerate(series):
            data=retention_curve(source,chosen,metric,mode)
            if data['관측 가능 사용자'].iloc[0]==0: continue
            fig.add_trace(go.Scatter(x=data['경과일'],y=data['비율(%)'],name=label,
                mode='lines+markers',line={'width':3,'color':colors[i%len(colors)]},marker={'size':4},
                customdata=data[['재방문 사용자','관측 가능 사용자']],
                hovertemplate=prefix+'%{x}<br>%{y:.2f}% · %{customdata[0]:,}/%{customdata[1]:,}명<extra>%{fullData.name}</extra>'))
        fig.update_layout(title={'text':title,'font':{'size':22}},height=430,
            margin={'l':35,'r':25,'t':70,'b':55},paper_bgcolor='white',plot_bgcolor='white',
            font={'size':15,'color':'#334155'},legend={'orientation':'h','y':-0.25},
            xaxis={'title':f'기준 구간 이후 경과 {unit} ({prefix})','dtick':5 if grain=='일별' else 1,'range':[0.8,horizon+0.2]},
            yaxis={'title':f'{"해당 "+unit if mode=="당일" else mode} 리텐션(%)','rangemode':'tozero','gridcolor':'#e2e8f0'},hovermode='x unified')
        if entities is not None and not series:
            st.info('비교할 분류를 선택해 주세요. 선택 가능한 분류가 없으면 기간 또는 최소 표본 수를 조정하세요.')
        elif not fig.data:
            st.warning(f'선택 범위에 {window}을 끝까지 관측할 수 있는 코호트가 없습니다. 기간을 넓히거나 시작일을 앞당겨 주세요.')
        st.plotly_chart(fig,width='stretch',key=chart_key,config={'displaylogo':False})

    st.markdown('### 구매자 vs 장바구니 이용자 vs 두 행동 사용자')
    compare=['buyer_return','cart_return','both_return']
    cards(compare)
    st.caption('장바구니 이용자에는 구매자도 포함됩니다. 두 집단은 서로 겹치며, 두 행동 사용자 집단은 각각의 첫 장바구니·첫 구매 중 늦은 날부터 추적합니다. 순차 퍼널 또는 같은 상품 조건은 요구하지 않습니다.')
    curves(compare,'행동 집단별 재방문율 비교','retention_behavior_curves')
    st.markdown('### 최초 방문·재구매·구매 후 재방문')
    core=['activity_return','purchase_repeat','buyer_return']
    cards(core)
    st.caption('최초 방문→재방문도 전체 방문자가 아닌 장바구니·구매 이력이 있는 집단 안에서 계산합니다. 집단 선택에 이후 행동 이력이 사용되는 회고적 비교이며, 신규 방문자 전체의 리텐션으로 해석하지 않습니다.')
    curves(core,'요청 지표별 리텐션','retention_core_curves')
    selected_stats=pack['stats'].loc[pack['stats']._entity==entity].copy()
    selected_stats['지표']=selected_stats.metric.map(lambda m:SPECS[m][0])
    selected_stats=selected_stats.drop(columns=['_entity','metric'])
    heatmap_table(display_columns(selected_stats),width='stretch',hide_index=True,
        column_config={window+' 비율(%)':st.column_config.NumberColumn(format='%.2f%%')})
    st.download_button('선택 범위 리텐션 요약 CSV',display_columns(selected_stats).to_csv(index=False).encode('utf-8-sig'),
        f'retention_{level}_{grain}_{start}_{cohort_end}_observed_{end}.csv','text/csv',key='retention_summary_download')

    st.divider()
    st.markdown('### 분류별 리텐션 비교')
    compare_level=st.radio('리텐션 비교 단위',['대분류','카테고리'],horizontal=True,key='retention_compare_level')
    group_key='root_categoryid' if compare_level=='대분류' else 'categoryid'
    comparison=cached(path,version,start,end,group_key)
    metric=st.selectbox('비교할 리텐션 지표',list(SPECS),format_func=lambda m:SPECS[m][0],key='retention_compare_metric')
    minimum=st.number_input('리텐션 최소 관측 가능 사용자',min_value=1,value=30,step=10,key='retention_minimum')
    eligible=comparison['stats'].loc[(comparison['stats'].metric==metric)&
        (comparison['stats']['30일 관측 가능 사용자']>=minimum)&(comparison['stats']._entity!=UNKNOWN)].sort_values('30일 관측 가능 사용자',ascending=False)
    options=eligible._entity.tolist()
    valid=[x for x in st.session_state.get('retention_compare_entities',options[:5]) if x in options]
    context=(group_key,metric,minimum,str(start),str(end),grain,str(cohort_end))
    if st.session_state.get('_retention_comparison_context')!=context:
        valid=valid or options[:5]
        st.session_state['_retention_comparison_context']=context
    st.session_state['retention_compare_entities']=valid[:5]
    chosen=st.multiselect('함께 볼 분류 · 최대 5개',options,format_func=fmt,max_selections=5,key='retention_compare_entities')
    curves([],f'{compare_level}별 {SPECS[metric][0]}','retention_compare_curves',comparison,
           [(x,metric,fmt(x)) for x in chosen])
    table=retention_columns(comparison,group_key)
    table=table.loc[table[group_key].isin(options)]
    table=display_columns(table)
    rate_cols={c:st.column_config.NumberColumn(format='%.2f%%') for c in table if c.endswith('(%)')}
    heatmap_table(table,width='stretch',hide_index=True,column_config=rate_cols)
    st.download_button('분류별 전체 리텐션 CSV',display_columns(retention_columns(comparison,group_key)).to_csv(index=False).encode('utf-8-sig'),
        f'retention_{group_key}_{grain}_{start}_{cohort_end}_observed_{end}.csv','text/csv',key='retention_compare_download')
    with st.expander('리텐션 정의와 관측 한계'):
        st.markdown(f'''
- 기준일은 전체 관측 이력의 최초 해당 행동일입니다. 기간 선택으로 첫 행동을 다시 설정하지 않습니다.
- 기본 {window} 재방문율은 {prefix}1~{prefix}{horizon} 중 같은 범위에서 한 번이라도 다시 활동한 비율입니다. 구매자·장바구니·두 행동 집단은 기준일이 서로 다릅니다.
- 곡선은 모든 경과일에 동일한 {window} 성숙 코호트를 사용합니다. {prefix}0는 제외하고, 같은 구간의 주문 여러 건도 재구매로 세지 않습니다.
- 재구매는 첫 구매 후 다른 UTC {unit} 구간의 구매입니다. 재방문은 조회·장바구니·구매 중 어떤 이벤트든 포함합니다.
- 대분류·카테고리는 각 이벤트 시점의 분류로 판단합니다. 다른 분류의 활동은 같은 분류 복귀로 세지 않습니다. 상품 단위는 같은 상품 복귀입니다.
- 미확인 분류는 별도로 남기며 미래 분류로 채우지 않습니다. 분류 이력 누락·변경 때문에 실제 복귀가 누락될 수 있습니다.
- 관측 시작 이전 이력이 없으므로 실제 신규 방문·최초 구매로 단정하지 않습니다. 초기 4주도 분석에 포함합니다.
- 집단은 중복될 수 있고 구매·장바구니 경험은 무작위 배정이 아니므로 비율 차이를 구매의 인과 효과로 해석하지 않습니다.
''')
