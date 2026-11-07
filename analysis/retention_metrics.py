"""UTC calendar daily/weekly/monthly retention in the same entity.

First anchors come from all available prior history, not reset by the calendar.
The calendar selects anchor cohorts and the observation end. D0 is excluded.
Behavior curves use one fully observable 30-day/4-week/3-month denominator.
Visit cohort matrices include all visitors and retain unknown future cells.
Any-first retention is a retrospective subset of users with cart/purchase by
the selected observation end, not retention of the entire visitor population.
"""
import numpy as np
import pandas as pd

DAY_MS = 86400000
CUTOFF_MS = 1442350800000
UNKNOWN = '__UNKNOWN__'
SPECS = {
    'activity_return': ('재방문율 · 행동 사용자', 'first_all', 'all'),
    'buyer_return': ('구매자 재방문율', 'first_buy', 'all'),
    'cart_return': ('장바구니 이용자 재방문율', 'first_cart', 'all'),
    'both_return': ('장바구니·구매 사용자 재방문율', 'first_both', 'all'),
    'purchase_repeat': ('재구매율', 'first_buy', 'purchase'),
}

GRAINS = {'일별': ('D', '일', 30), '주별': ('W', '주', 4), '월별': ('M', '개월', 3)}


def period_ids(days, grain):
    if grain == '일별':
        return days.astype('int64')
    if grain == '주별':
        return ((days + 3) // 7).astype('int64')  # Monday-based UTC weeks.
    dates = pd.to_datetime(days * DAY_MS, unit='ms')
    return (dates.dt.year * 12 + dates.dt.month - 1).astype('int64')


def period_end(ids, grain):
    if grain == '일별':
        return ids
    if grain == '주별':
        return ids * 7 + 3
    dates = pd.to_datetime(pd.DataFrame({'year': ids // 12, 'month': ids % 12 + 1, 'day': 1}))
    return ((dates + pd.offsets.MonthEnd(0)).dt.as_unit('ms').astype('int64') // DAY_MS)


def visit_cohorts(events, key, entity, start, end, grain='일별', cohort_end=None):
    """All visitors, first observed visit cohorts, exact period returns including 0."""
    start_day, last_complete, end_exclusive = observation_days(start, end)
    e = events.loc[(events.timestamp < end_exclusive) & (events.day <= last_complete)]
    if key is not None:
        e = e.loc[e[key] == entity]
    first = e.groupby('visitorid', observed=True).day.min().rename('anchor')
    first = first.loc[first >= start_day].to_frame()
    if cohort_end is not None:
        final_anchor = int(pd.Timestamp(cohort_end,tz='UTC').timestamp()*1000)//DAY_MS
        first = first.loc[first.anchor <= final_anchor]
    first['cohort'] = period_ids(first.anchor, grain)
    size = first.groupby('cohort').size()
    daily = e[['visitorid', 'day']].merge(first, on='visitorid', validate='many_to_one')
    daily['period'] = period_ids(daily.day, grain)
    daily['n'] = daily.period - daily.cohort
    counts = daily.drop_duplicates(['visitorid', 'n']).groupby(['cohort', 'n']).size()
    maximum = int(period_ids(pd.Series([last_complete]), grain).iloc[0] - size.index.min()) if len(size) else 0
    records = []
    for cohort, denominator in size.items():
        end_day = int(period_end(pd.Series([cohort]), grain).iloc[0])
        end_date = pd.to_datetime(end_day * DAY_MS, unit='ms')
        label = (end_date - pd.Timedelta(days=6)).strftime('%Y-%m-%d') if grain == '주별' else end_date.strftime('%Y-%m' if grain == '월별' else '%Y-%m-%d')
        for n in range(maximum + 1):
            complete = n == 0 or int(period_end(pd.Series([cohort + n]), grain).iloc[0]) <= last_complete
            count = int(counts.get((cohort, n), 0)) if complete else np.nan
            records.append((label, n, int(denominator), count, count / denominator * 100))
    return pd.DataFrame(records, columns=['방문 코호트', 'N', '코호트 사용자', '재방문 사용자', '비율(%)'])


def load_retention_events(path):
    events = pd.read_csv(path,usecols=['timestamp','visitorid','event','itemid','categoryid','root_categoryid'],
        dtype={'timestamp':'int64','visitorid':'int64','event':'category',
               'itemid':'string','categoryid':'string','root_categoryid':'string'})
    events = events.loc[events.timestamp<=CUTOFF_MS].copy()
    events['day'] = events.timestamp//DAY_MS
    events['date'] = pd.to_datetime(events.day*DAY_MS,unit='ms')
    for key in ['categoryid','root_categoryid']:
        events[key] = events[key].fillna(UNKNOWN)
    return events


def scope_events(events,root=None,category=None):
    selected=events
    if root is not None: selected=selected.loc[selected.root_categoryid==root]
    if category is not None: selected=selected.loc[selected.categoryid==category]
    return selected


def observation_days(start,end):
    start_day=int(pd.Timestamp(start,tz='UTC').timestamp()*1000)//DAY_MS
    end_exclusive=min(int((pd.Timestamp(end,tz='UTC')+pd.Timedelta(days=1)).timestamp()*1000),CUTOFF_MS+1)
    # The partial final UTC date is never treated as a fully observed day.
    return start_day,end_exclusive//DAY_MS-1,end_exclusive


def retention_pack(events,key,start,end,grain='일별',cohort_end=None):
    first_day,last_complete,end_exclusive=observation_days(start,end)
    horizon = GRAINS[grain][2]
    e=events.loc[events.timestamp<end_exclusive].copy()
    if key is None:
        e['_entity']='전체'
    else:
        e['_entity']=e[key].fillna(UNKNOWN)
    group=['visitorid','_entity']
    first=e.groupby(group,observed=True).day.min().rename('first_all').to_frame()
    for name,event in [('first_cart','addtocart'),('first_buy','transaction')]:
        first[name]=e.loc[e.event==event].groupby(group,observed=True).day.min()
    # A user belongs to this retrospective behavior population only if one of
    # these actions was observed at/before the selected observation end.
    first=first.loc[first.first_cart.notna()|first.first_buy.notna()].copy()
    first['first_both']=first[['first_cart','first_buy']].max(axis=1).where(first[['first_cart','first_buy']].notna().all(axis=1))
    first=first.reset_index()
    entities=first['_entity'].drop_duplicates()
    daily_all=e[group+['day']].merge(first[group],on=group,validate='many_to_one').drop_duplicates()
    daily_buy=e.loc[e.event=='transaction',group+['day']].drop_duplicates()
    statistics=[]
    hits=[]
    for metric,(_,anchor_name,target) in SPECS.items():
        anchors=first.loc[first[anchor_name].notna(),group+[anchor_name]].rename(columns={anchor_name:'anchor'})
        # Keep the original first-event date for cohort selection; convert to
        # calendar periods only after selecting anchors. Never reset old users.
        candidates=anchors.loc[anchors.anchor>=first_day]
        if cohort_end is not None:
            final_anchor = int(pd.Timestamp(cohort_end,tz='UTC').timestamp()*1000)//DAY_MS
            candidates = candidates.loc[candidates.anchor <= final_anchor]
        candidates = candidates.copy()
        candidates['anchor'] = period_ids(candidates.anchor, grain)
        anchors=candidates.loc[period_end(candidates.anchor+horizon, grain)<=last_complete].copy()
        anchors['anchor']=anchors.anchor.astype('int64')
        followup=(daily_buy if target=='purchase' else daily_all).merge(anchors,on=group,validate='many_to_one')
        followup['n']=period_ids(followup.day, grain)-followup.anchor
        followup=followup.loc[followup.n.between(1,horizon)].drop_duplicates(group+['n'])
        earliest=followup.groupby(group,observed=True).n.min().reset_index()
        stats=pd.DataFrame({'_entity':entities})
        stats['metric']=metric
        for col,source in [('코호트 사용자',candidates),('30일 관측 가능 사용자',anchors),('30일 재방문 사용자',earliest)]:
            counts=source.groupby('_entity',observed=True).size()
            stats[col]=stats['_entity'].map(counts).fillna(0).astype('int64')
        stats['추적 부족 제외 사용자']=stats['코호트 사용자']-stats['30일 관측 가능 사용자']
        stats['30일 비율(%)']=stats['30일 재방문 사용자']/stats['30일 관측 가능 사용자'].replace(0,np.nan)*100
        assert stats['30일 재방문 사용자'].le(stats['30일 관측 가능 사용자']).all()
        statistics.append(stats)
        exact=followup.groupby(['_entity','n'],observed=True).size().rename('당일 사용자')
        cumulative=earliest.groupby(['_entity','n'],observed=True).size().rename('최초 재방문 사용자')
        point=pd.concat([exact,cumulative],axis=1).fillna(0).astype('int64').reset_index()
        point['metric']=metric
        hits.append(point)
    return {'stats':pd.concat(statistics,ignore_index=True),
            'hits':pd.concat(hits,ignore_index=True),
            'last_complete':last_complete,'start_day':first_day,'grain':grain,'horizon':horizon}


def metric_row(pack,entity,metric):
    rows=pack['stats'].loc[(pack['stats']._entity==entity)&(pack['stats'].metric==metric)]
    if rows.empty:
        return {'코호트 사용자':0,'30일 관측 가능 사용자':0,
                '30일 재방문 사용자':0,'추적 부족 제외 사용자':0,'30일 비율(%)':np.nan}
    return rows.iloc[0].to_dict()


def retention_curve(pack,entity,metric,mode='누적'):
    row=metric_row(pack,entity,metric)
    points=pack['hits'].loc[(pack['hits']._entity==entity)&(pack['hits'].metric==metric)].set_index('n')
    days=pd.Index(range(1,pack.get('horizon',30)+1),name='경과일')
    if mode=='누적':
        counts=points['최초 재방문 사용자'].reindex(days,fill_value=0).cumsum()
    else:
        counts=points['당일 사용자'].reindex(days,fill_value=0)
    result=pd.DataFrame({'경과일':days,'재방문 사용자':counts.to_numpy(dtype='int64'),
                         '관측 가능 사용자':row['30일 관측 가능 사용자']})
    denominator=row['30일 관측 가능 사용자']
    result['비율(%)']=result['재방문 사용자']/denominator*100 if denominator else np.nan
    if mode=='누적':
        assert result['재방문 사용자'].iloc[-1]==row['30일 재방문 사용자']
    return result


def retention_columns(pack,key):
    base=pack['stats'][['_entity']].drop_duplicates().rename(columns={'_entity':key})
    names={
        'activity_return':('30일 재방문율(%)','30일 관측 가능 사용자'),
        'buyer_return':('구매자 30일 재방문율(%)','구매자 30일 관측 가능 사용자'),
        'cart_return':('장바구니 30일 재방문율(%)','장바구니 30일 관측 가능 사용자'),
        'both_return':('장바구니·구매 30일 재방문율(%)','장바구니·구매 30일 관측 가능 사용자'),
        'purchase_repeat':('30일 재구매율(%)','재구매 30일 관측 가능 사용자')}
    for metric,(rate,denominator) in names.items():
        sub=pack['stats'].loc[pack['stats'].metric==metric,['_entity','30일 비율(%)','30일 관측 가능 사용자']]
        sub=sub.rename(columns={'_entity':key,'30일 비율(%)':rate,'30일 관측 가능 사용자':denominator})
        base=base.merge(sub,on=key,how='left',validate='one_to_one')
    return base
