"""First observed view rankings at root/category/item level, within selected dates.

Count each visitor once per entity (equivalent to retaining its first view).
Branch filters precede deduplication. Global top tens are independent of filters.
Unknown hierarchy values stay unknown; item rankings still include those items.
"""
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from analysis.table_styles import heatmap_table
from analysis.retention_service import cached_retention
from analysis.retention_metrics import metric_row,retention_columns
from analysis.data_files import processed_file

UNKNOWN = '__UNKNOWN__'
LEVELS = [('대분류', 'root_categoryid', '#2563eb'),
          ('카테고리', 'categoryid', '#0891b2'),
          ('아이템', 'itemid', '#7c3aed')]


def load_category_events(path):
    df = pd.read_csv(path, usecols=['timestamp', 'visitorid', 'event', 'itemid', 'categoryid', 'root_categoryid'],
                     dtype={'timestamp': 'int64', 'visitorid': 'int64', 'event': 'category',
                            'itemid': 'string', 'categoryid': 'string', 'root_categoryid': 'string'})
    df = df.loc[df['timestamp'] <= 1442350800000].copy()
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_localize(None).dt.normalize()
    return df


def load_views(path):
    df = load_category_events(path)
    return df.loc[df['event'] == 'view']


def conversion_views(events):
    """Attribute later same-item actions to the view-time category.

    max(action time) > view time means at least one later action exists.
    Actions and views must both be within the selected analysis period.
    Purchases do not require an intermediate cart. No session/time-window cap.
    """
    views = events.loc[events['event'] == 'view'].copy()
    keys = ['visitorid', 'itemid']
    for event, flag in [('addtocart', '_cart'), ('transaction', '_purchase')]:
        times = events.loc[events['event'] == event].groupby(keys, observed=True)['timestamp'].max()
        lookup = pd.MultiIndex.from_frame(views[keys])
        last = times.reindex(lookup).to_numpy()
        views[flag] = last > views['timestamp'].to_numpy()
    return views


def ranking(df, key):
    result = df.groupby(key, observed=True)['visitorid'].nunique().rename('첫 조회 방문자 수').reset_index()
    for flag, label in [('_cart', '장바구니 전환 방문자 수'), ('_purchase', '구매 전환 방문자 수')]:
        converted = df.loc[df[flag]].groupby(key, observed=True)['visitorid'].nunique() if flag in df else pd.Series(dtype='int64')
        result[label] = result[key].map(converted).fillna(0).astype('int64')
    result['장바구니 전환율(%)'] = result['장바구니 전환 방문자 수'] / result['첫 조회 방문자 수'] * 100
    result['구매 전환율(%)'] = result['구매 전환 방문자 수'] / result['첫 조회 방문자 수'] * 100
    result = result.sort_values(['첫 조회 방문자 수', key], ascending=[False, True]).reset_index(drop=True)
    result.insert(0, '순위', range(1, len(result)+1))
    return result


def branch(df, key, selected):
    mask = df[key].isna() if selected == UNKNOWN else df[key].eq(selected).fillna(False)
    return df.loc[mask]


def render_category_tab(root, start, end):
    path = processed_file(root, 'events_with_category.csv')
    st.subheader('카테고리별 첫 조회 성과')
    st.caption('방문자별 각 대분류·카테고리·상품의 첫 조회를 1건으로 집계합니다. 같은 대상의 반복 조회는 제외합니다.')
    if not path.is_file():
        st.info('카테고리가 연결된 이벤트 파일을 먼저 생성해 주세요.')
        return
    version = (path.stat().st_mtime_ns, path.stat().st_size)

    @st.cache_resource(max_entries=1, show_spinner='카테고리 조회 데이터를 불러오는 중입니다…')
    def cached_views(path_string, version):
        return load_category_events(path_string)

    @st.cache_resource(max_entries=2, show_spinner='기간별 첫 조회 성과를 계산하는 중입니다…')
    def period_views(path_string, version, start, end):
        views = cached_views(path_string, version)
        selected = conversion_views(views.loc[views['date'].between(pd.Timestamp(start), pd.Timestamp(end))])
        ranks = {key: ranking(selected, key) for _, key, _ in LEVELS}
        return selected, ranks

    views, cached_ranks = period_views(str(path), version, start, end)
    # cache_resource results are shared: never enrich its frames in place.
    ranks = {key: table.copy() for key, table in cached_ranks.items()}
    if views.empty:
        st.info('선택 기간에 상품 조회 기록이 없습니다.')
        return
    retention_total=cached_retention(str(path),version,start,end)
    def enrich(table,pack,key):
        result=table.merge(retention_columns(pack,key),on=key,how='left',validate='one_to_one')
        for column in result:
            if '관측 가능 사용자' in column: result[column]=result[column].fillna(0).astype('int64')
        leading=['순위',key,'첫 조회 방문자 수','30일 재방문율(%)','30일 관측 가능 사용자',
                 '장바구니 전환율(%)','구매 전환율(%)']
        return result[leading+[column for column in result if column not in leading]]
    for _,key,_ in LEVELS:
        ranks[key]=enrich(ranks[key],cached_retention(str(path),version,start,end,key),key)
    st.markdown('**집계 기준:** 선택 기간 안에서 대상별 첫 관측 조회입니다. 한 방문자가 여러 대상에 각각 포함될 수 있으며, 실제 생애 최초 조회를 의미하지 않습니다.')
    st.caption('전환율 = 첫 조회 방문자 중 같은 상품을 조회한 이후 장바구니 추가 또는 구매한 방문자 비율. 조회와 전환 모두 선택 기간 내 기록만 사용하며, 구매는 장바구니 경유를 요구하지 않습니다.')
    viewers = views['visitorid'].nunique()
    cart_users = views.loc[views['_cart'], 'visitorid'].nunique()
    purchase_users = views.loc[views['_purchase'], 'visitorid'].nunique()
    a, b, c, d = st.columns(4)
    a.metric('첫 조회 방문자', f'{viewers:,}명')
    b.metric('장바구니 전환율', f'{cart_users/viewers*100:.2f}%')
    b.caption(f'{cart_users:,}명 / {viewers:,}명')
    c.metric('구매 전환율', f'{purchase_users/viewers*100:.2f}%')
    c.caption(f'{purchase_users:,}명 / {viewers:,}명')
    retention_row=metric_row(retention_total,'전체','activity_return')
    value=retention_row['30일 비율(%)']
    d.metric('30일 재방문율',f'{value:.2f}%' if pd.notna(value) else '—')
    d.caption(f"행동 사용자 {retention_row['30일 재방문 사용자']:,}명 / {retention_row['30일 관측 가능 사용자']:,}명")
    st.caption('30일 재방문은 장바구니 또는 구매 이력이 있는 사용자만 대상입니다. 전체 이력의 첫 행동일을 기준으로 D1~D30을 완전히 관측한 코호트이므로, 첫 조회 방문자 수와 분모가 다릅니다.')
    st.caption('위 카드는 미확인 분류를 포함한 전체 조회 방문자 기준이며, 아래 순위는 각 대상별로 중복을 제거합니다.')
    metric = st.radio('순위·그래프 기준', ['첫 조회 방문자 수', '장바구니 전환율(%)', '구매 전환율(%)','30일 재방문율(%)'], horizontal=True, key='category_rank_metric')
    st.caption('전환율은 조회 방문자가 적으면 크게 변동할 수 있습니다. 순위표의 분모와 전환 방문자 수도 함께 확인하세요.')

    def sorted_rank(table):
        table = table.sort_values([metric, '첫 조회 방문자 수'] if metric != '첫 조회 방문자 수' else [metric], ascending=False, kind='stable').copy()
        table['순위'] = range(1, len(table)+1)
        return table

    rate_columns = {name: st.column_config.NumberColumn(name, format='%.2f%%') for name in ranks['categoryid'] if name.endswith('(%)')}
    unknown = int(views['categoryid'].isna().sum())
    st.caption(f'카테고리 미확인 조회 {unknown:,}건은 대분류·카테고리 순위에서 제외되지만, 상품 순위에는 포함됩니다. 분류명 정보가 없어 ID로 표시합니다.')

    def chart(table, key, title, color, chart_key, limit=10):
        table=table.loc[table[metric].notna()]
        if table.empty:
            st.info('집계 가능한 항목이 없습니다. 30일 재방문율은 추적 기간을 확보한 코호트가 필요합니다.')
            return
        top = sorted_rank(table).head(limit).iloc[::-1]
        labels = ['ID ' + str(x) for x in top[key]]
        rate = metric.endswith('(%)')
        text = [f'{v:.2f}%' if rate else f'{v:,}명' for v in top[metric]]
        fig = go.Figure(go.Bar(x=top[metric], y=labels, orientation='h',
                              customdata=top[['첫 조회 방문자 수','장바구니 전환 방문자 수','구매 전환 방문자 수','장바구니 전환율(%)','구매 전환율(%)','30일 재방문율(%)','30일 관측 가능 사용자']],
                              marker_color=color, text=text,
                              textposition='outside', cliponaxis=False,
                              hovertemplate='%{y}<br>첫 조회 %{customdata[0]:,}명<br>장바구니 전환 %{customdata[1]:,}명 (%{customdata[3]:.2f}%)<br>구매 전환 %{customdata[2]:,}명 (%{customdata[4]:.2f}%)<br>30일 재방문 %{customdata[5]:.2f}% · 관측 가능 %{customdata[6]:,}명<extra></extra>'))
        fig.update_layout(title={'text': title, 'font': {'size': 20}}, height=430,
                          margin={'l': 15, 'r': 80, 't': 65, 'b': 35},
                          paper_bgcolor='white', plot_bgcolor='white',
                          font={'size': 14, 'color': '#334155'},
                          xaxis={'title': metric, 'gridcolor': '#e2e8f0',
                                 'range': [0, max(float(top[metric].max())*1.4, 1)]},
                          yaxis={'type': 'category', 'automargin': True})
        st.plotly_chart(fig, width='stretch', key=chart_key, config={'displaylogo': False})

    st.markdown('### 주요 성과 · 전체 순위 TOP 10')
    st.caption('아래 세 순위는 상단의 기간 선택을 적용한 전체 순위입니다. 하단의 대분류·카테고리 선택과는 독립적입니다.')
    for column, (label, key, color) in zip(st.columns(3), LEVELS):
        with column:
            chart(ranks[key], key, f'{label} TOP 10', color, f'global_{key}')
            heatmap_table(sorted_rank(ranks[key]).head(10), hide_index=True, width='stretch', column_config=rate_columns)
            with st.expander(f'{label} 순위표 및 다운로드'):
                st.download_button('전체 순위 CSV', sorted_rank(ranks[key]).to_csv(index=False).encode('utf-8-sig'),
                                   f'{key}_first_views_{start}_{end}.csv', 'text/csv', key=f'csv_{key}')

    st.divider()
    st.markdown('### 상세 탐색 · 대분류 → 카테고리 → 상품')
    root_options = ranks['root_categoryid']['root_categoryid'].tolist()
    if views['root_categoryid'].isna().any(): root_options.append(UNKNOWN)
    format_id = lambda value: '미확인' if value == UNKNOWN else f'ID {value}'
    # Reset dependent widgets before creation when date or parent selection changes.
    if st.session_state.get('category_root') not in root_options:
        st.session_state['category_root'] = root_options[0]
    selected_root = st.selectbox('1. 대분류 선택', root_options, format_func=format_id, key='category_root')
    root_views = branch(views, 'root_categoryid', selected_root)
    category_rank = enrich(ranking(root_views, 'categoryid'),cached_retention(str(path),version,start,end,'categoryid',root=selected_root),'categoryid')
    category_options = category_rank['categoryid'].tolist()
    if root_views['categoryid'].isna().any(): category_options.append(UNKNOWN)
    if not category_options:
        st.info('이 대분류에 연결된 카테고리가 없습니다.')
        return
    if st.session_state.get('category_child') not in category_options:
        st.session_state['category_child'] = category_options[0]
    selected_category = st.selectbox('2. 카테고리 선택', category_options,
                                    format_func=format_id, key='category_child')
    item_views = branch(root_views, 'categoryid', selected_category)
    item_rank = enrich(ranking(item_views, 'itemid'),cached_retention(str(path),version,start,end,'itemid',root=selected_root,category=selected_category),'itemid')
    st.markdown(f'**현재 경로:** 대분류 {format_id(selected_root)} → 카테고리 {format_id(selected_category)}')
    detail_retention=cached_retention(str(path),version,start,end,None,root=selected_root,category=selected_category)
    for column,cohort,label in zip(st.columns(3),['buyer_return','cart_return','both_return'],
        ['선택 경로 구매자 30일 재방문율','선택 경로 장바구니 30일 재방문율','선택 경로 두 행동 사용자 30일 재방문율']):
        r=metric_row(detail_retention,'전체',cohort);v=r['30일 비율(%)']
        column.metric(label,f'{v:.2f}%' if pd.notna(v) else '—')
        column.caption(f"{r['30일 재방문 사용자']:,}명 / {r['30일 관측 가능 사용자']:,}명")
    detail_users = item_views['visitorid'].nunique()
    da, db, dc = st.columns(3)
    da.metric('선택 경로 첫 조회 방문자', f'{detail_users:,}명')
    for column, flag, label in [(db, '_cart', '선택 경로 장바구니 전환율'), (dc, '_purchase', '선택 경로 구매 전환율')]:
        converted = item_views.loc[item_views[flag], 'visitorid'].nunique()
        column.metric(label, f'{converted/detail_users*100:.2f}%' if detail_users else '—')
        column.caption(f'{converted:,}명 / {detail_users:,}명')
    left, right = st.columns(2)
    with left:
        chart(category_rank, 'categoryid', '선택 대분류의 카테고리 TOP 10', '#0891b2', 'detail_categories')
    with right:
        chart(item_rank, 'itemid', '선택 카테고리의 상품 TOP 10', '#7c3aed', 'detail_items')
    with st.expander('상세 순위표 보기'):
        st.markdown('**선택 대분류의 전체 카테고리**')
        heatmap_table(sorted_rank(category_rank), width='stretch', hide_index=True, column_config=rate_columns)
        st.markdown('**선택 경로의 전체 상품**')
        heatmap_table(sorted_rank(item_rank), width='stretch', hide_index=True, column_config=rate_columns)
        st.download_button('선택 경로 상품 순위 CSV', sorted_rank(item_rank).to_csv(index=False).encode('utf-8-sig'),
                           f'items_{selected_root}_{selected_category}_{start}_{end}.csv', 'text/csv', key='detail_items_csv')
    with st.expander('전환 집계 기준 자세히 보기'):
        st.markdown('''
- 분모: 선택 범위에서 해당 대분류·카테고리·상품을 조회한 고유 방문자 수.
- 분자: 같은 상품 조회보다 시각이 엄격히 늦은 장바구니 추가·구매가 있는 고유 방문자 수. 반복 행동은 한 번만 셉니다.
- 상품의 분류가 바뀐 경우 조회 당시 분류에 전환을 귀속합니다. 서로 다른 상품의 조회와 전환은 연결하지 않습니다.
- 구매 전환율의 분모도 첫 조회 방문자입니다. 장바구니에서 구매로의 단계 전환율과는 다릅니다.
- 세션·전환 기한 제한은 없으며, 선택 기간 이전 조회·이후 전환은 연결하지 않습니다.
- 관측 시작 이전 이력과 종료 이후 행동을 알 수 없으므로 실제 생애 최초 조회 또는 최종 전환율로 단정하지 않습니다.
''')
