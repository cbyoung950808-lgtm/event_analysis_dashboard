"""24h ordered same-item funnels, attributed to the first view's category.

All stages must be inside selected dates and <=24h from first observed view
per visitor/item. Strictly increasing stage timestamps; no reset on later views.
Visitors count once per scope/stage. Distribution samples choose the earliest
completion per visitor/scope, keeping that transition's same-item path intact.
"""
import numpy as np
import pandas as pd
from analysis.category_dashboard import load_category_events

WINDOW_MS = 24 * 3600 * 1000
UNKNOWN = '__UNKNOWN__'
KEYS = ['visitorid', 'itemid']
RATE_COLS = ['조회→장바구니(%)', '장바구니→구매(%)', '조회→구매(%)']


def build_paths(events):
    views = events.loc[events.event == 'view']
    first = views.sort_values('timestamp', kind='stable').drop_duplicates(KEYS)
    paths = first[KEYS+['timestamp','root_categoryid','categoryid']].rename(columns={'timestamp':'view_time'}).reset_index(drop=True)
    paths['_path'] = np.arange(len(paths))
    for key in ['root_categoryid','categoryid']:
        paths[key] = paths[key].fillna(UNKNOWN)
    carts = events.loc[events.event == 'addtocart', KEYS+['timestamp']].merge(paths[KEYS+['view_time']],on=KEYS,validate='many_to_one')
    carts = carts.loc[(carts.timestamp>carts.view_time) & (carts.timestamp-carts.view_time<=WINDOW_MS)]
    cart_times = carts.groupby(KEYS, as_index=False)['timestamp'].min().rename(columns={'timestamp':'cart_time'})
    paths = paths.merge(cart_times,on=KEYS,how='left',validate='one_to_one')
    purchases = events.loc[events.event == 'transaction',KEYS+['timestamp']].merge(
        paths.loc[paths.cart_time.notna(),KEYS+['view_time','cart_time']],on=KEYS,validate='many_to_one')
    purchases = purchases.loc[(purchases.timestamp>purchases.cart_time) & (purchases.timestamp-purchases.view_time<=WINDOW_MS)]
    purchase_times = purchases.groupby(KEYS,as_index=False)['timestamp'].min().rename(columns={'timestamp':'purchase_time'})
    paths = paths.merge(purchase_times,on=KEYS,how='left',validate='one_to_one')
    # Count observed prior-stage actions on each eligible same-item path.
    for stage, end, flag in [('view','cart_time','views_before_cart'),('addtocart','purchase_time','carts_before_purchase')]:
        lower = 'view_time' if stage=='view' else 'cart_time'
        eligible = paths.loc[paths[end].notna(),KEYS+['_path',lower,end]]
        actions = events.loc[events.event==stage,KEYS+['timestamp']].merge(eligible,on=KEYS,validate='many_to_one')
        prior = actions.loc[(actions.timestamp>=actions[lower]) & (actions.timestamp<actions[end])]
        counts = prior.groupby('_path').size()
        paths[flag] = paths['_path'].map(counts).astype('Int64')
        assert paths.loc[paths[end].notna(),flag].ge(1).all()
    paths['view_to_cart_min'] = (paths.cart_time-paths.view_time)/60000
    paths['cart_to_purchase_min'] = (paths.purchase_time-paths.cart_time)/60000
    paths['view_to_purchase_min'] = (paths.purchase_time-paths.view_time)/60000
    assert paths.loc[paths.purchase_time.notna(),'cart_time'].notna().all()
    assert paths.loc[paths.cart_time.notna(),'view_to_cart_min'].between(0,1440,inclusive='right').all()
    assert paths.loc[paths.purchase_time.notna(),'view_to_purchase_min'].between(0,1440,inclusive='right').all()
    return paths


def representative(paths, stage, key=None):
    """Earliest completed cart or purchase per visitor/entity, deterministic ties."""
    endpoint = 'cart_time' if stage=='cart' else 'purchase_time'
    subset = ['visitorid'] + ([key] if key else [])
    return paths.loc[paths[endpoint].notna()].sort_values([endpoint,'view_time','itemid'],kind='stable').drop_duplicates(subset)


def summary(paths, key=None):
    working = paths if key else paths.assign(scope='전체')
    group_key = key or 'scope'
    cart = representative(working,'cart',group_key)
    purchase = representative(working,'purchase',group_key)
    result = working.groupby(group_key,observed=True).visitorid.nunique().rename('조회 방문자').to_frame()
    result['장바구니 방문자'] = cart.groupby(group_key,observed=True).visitorid.nunique()
    result['구매 방문자'] = purchase.groupby(group_key,observed=True).visitorid.nunique()
    result[['장바구니 방문자','구매 방문자']] = result[['장바구니 방문자','구매 방문자']].fillna(0).astype('int64')
    result[RATE_COLS[0]] = result['장바구니 방문자']/result['조회 방문자']*100
    result[RATE_COLS[1]] = result['구매 방문자']/result['장바구니 방문자'].replace(0,np.nan)*100
    result[RATE_COLS[2]] = result['구매 방문자']/result['조회 방문자']*100
    for rows, column, output in [
        (cart,'view_to_cart_min','조회→장바구니 중앙값(분)'),
        (purchase,'cart_to_purchase_min','장바구니→구매 중앙값(분)'),
        (purchase,'view_to_purchase_min','조회→구매 중앙값(분)'),
        (cart,'views_before_cart','장바구니 전 조회 횟수 중앙값'),
        (purchase,'carts_before_purchase','구매 전 장바구니 횟수 중앙값')]:
        result[output] = rows.groupby(group_key,observed=True)[column].median()
    assert (result['조회 방문자']>=result['장바구니 방문자']).all()
    assert (result['장바구니 방문자']>=result['구매 방문자']).all()
    return result.reset_index().sort_values('조회 방문자',ascending=False,kind='stable').reset_index(drop=True)


def distribution(rows, column, kind='time'):
    values = rows[column].dropna().astype(float)
    if kind=='time':
        edges=[0,1,5,15,30,60,180,360,720,1440]
        labels=['1분 이하','1~5분','5~15분','15~30분','30~60분','1~3시간','3~6시간','6~12시간','12~24시간']
    else:
        edges=[0,1,2,3,4,5,10,np.inf]
        labels=['1회','2회','3회','4회','5회','6~10회','11회 이상']
    counts = pd.cut(values,edges,labels=labels,include_lowest=True,right=True).value_counts(sort=False)
    result = pd.DataFrame({'구간':labels,'방문자 수':counts.to_numpy(dtype='int64')})
    assert result['방문자 수'].sum()==len(values)
    return result


def prepare(path,start,end):
    events = load_category_events(path)
    events = events.loc[events.date.between(pd.Timestamp(start),pd.Timestamp(end))]
    return build_paths(events)
