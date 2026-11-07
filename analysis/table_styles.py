"""Column-wise heatmaps for dashboard tables; underlying values stay unchanged."""
import pandas as pd
import streamlit as st

EXCLUDED = {'id','visitorid','itemid','categoryid','root_categoryid','순위',
            'timestamp','effective_timestamp','년도','월','일'}


def heatmap_style(frame):
    numeric = [column for column in frame.columns
               if str(column).lower() not in EXCLUDED
               and pd.api.types.is_numeric_dtype(frame[column])]
    # Explicit RGB interpolation avoids a plotting dependency and provides
    # readable white text on darker cells. Each displayed column has its own scale.
    def column_styles(series):
        valid = series.dropna()
        if valid.empty:
            return ['background-color: #f1f5f9; color: #64748b;'] * len(series)
        low, high = float(valid.min()), float(valid.max())
        styles = []
        for value in series:
            if pd.isna(value):
                styles.append('background-color: #f1f5f9; color: #64748b;')
                continue
            weight = (float(value)-low)/(high-low) if high>low else .12
            start, end = (239,246,255), (29,78,216)
            rgb = tuple(round(a+(b-a)*weight) for a,b in zip(start,end))
            foreground = '#ffffff' if weight >= .6 else '#0f172a'
            styles.append(f'background-color: #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}; color: {foreground};')
        return styles

    formatters = {}
    for column in numeric:
        formatters[column] = '{:,.0f}' if pd.api.types.is_integer_dtype(frame[column]) else '{:,.2f}'
    style = frame.style.format(formatters, na_rep='—')
    if numeric:
        style = style.apply(column_styles, axis=0, subset=numeric)
    return style


def heatmap_table(frame, **kwargs):
    # Large item drilldowns must not hit pandas' default Styler cell limit.
    with pd.option_context('styler.render.max_elements', max(262144, frame.size)):
        result = st.dataframe(heatmap_style(frame), **kwargs)
    st.caption('열별 비교: 값이 클수록 진한 파랑 · 회색은 결측 · 색 농도는 성과의 좋고 나쁨을 뜻하지 않습니다.')
    return result
