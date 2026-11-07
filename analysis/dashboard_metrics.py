"""UTC event aggregation. Distinct counts are recalculated per period."""
import pandas as pd

METRICS = {
    '활성 사용자 수': ('명', '#2563eb'),
    '구매자 수': ('명', '#0891b2'),
    '구매 횟수': ('회', '#7c3aed'),
    '장바구니에 담은 횟수': ('회', '#ea580c'),
    '이벤트 횟수': ('건', '#059669'),
}
CUTOFF = pd.Timestamp('2015-09-15 21:00:00', tz='UTC')


def load_events(path):
    frame = pd.read_csv(path, usecols=['timestamp', 'visitorid', 'event', 'transactionid'],
                        dtype={'timestamp': 'int64', 'visitorid': 'int64',
                               'event': 'category', 'transactionid': 'string'})
    # IDs are grouping keys only. Never used as numerical explanatory variables.
    frame['time'] = pd.to_datetime(frame['timestamp'], unit='ms', utc=True)
    frame = frame.loc[frame['time'] <= CUTOFF].copy()
    frame['date'] = frame['time'].dt.tz_localize(None).dt.normalize()
    return frame


def totals(frame):
    purchases = frame.loc[frame['event'] == 'transaction']
    return {
        '활성 사용자 수': int(frame['visitorid'].nunique()),
        '구매자 수': int(purchases['visitorid'].nunique()),
        '구매 횟수': int(purchases['transactionid'].nunique()),
        '장바구니에 담은 횟수': int((frame['event'] == 'addtocart').sum()),
        '이벤트 횟수': len(frame),
    }


def trend(frame, start, end, frequency):
    """Zero-fill days/months within selected dates, including empty selections."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if frequency == 'MS':
        start = start.replace(day=1)
        end = end.replace(day=1)
    index = pd.date_range(start, end, freq=frequency)
    def grouped(subset):
        return subset.groupby(pd.Grouper(key='date', freq=frequency))
    purchase = frame.loc[frame['event'] == 'transaction']
    cart = frame.loc[frame['event'] == 'addtocart']
    result = pd.DataFrame({
        '활성 사용자 수': grouped(frame)['visitorid'].nunique(),
        '구매자 수': grouped(purchase)['visitorid'].nunique(),
        '구매 횟수': grouped(purchase)['transactionid'].nunique(),
        '장바구니에 담은 횟수': grouped(cart).size(),
        '이벤트 횟수': grouped(frame).size(),
    }).reindex(index).fillna(0).astype('int64')
    result.index.name = '일자' if frequency == 'D' else '월'
    return result


def summarize(frame, start, end):
    selected = frame.loc[frame['date'].between(pd.Timestamp(start), pd.Timestamp(end))]
    return totals(selected), trend(selected, start, end, 'D'), trend(selected, start, end, 'MS')
