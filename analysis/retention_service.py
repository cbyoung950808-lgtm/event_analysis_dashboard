"""Shared read-only source and compressed retention caches for both tabs."""
import streamlit as st
from analysis.retention_metrics import load_retention_events,retention_pack,scope_events,visit_cohorts


@st.cache_resource(max_entries=1,show_spinner='리텐션 분석용 행동 이력을 불러오는 중입니다…')
def retention_events(path,version):
    return load_retention_events(path)


@st.cache_resource(max_entries=12,show_spinner='선택한 시간 단위의 코호트와 리텐션을 계산하는 중입니다…')
def cached_retention(path,version,start,end,key=None,root=None,category=None,grain='일별',cohort_end=None):
    events=scope_events(retention_events(path,version),root,category)
    return retention_pack(events,key,start,end,grain,cohort_end)


@st.cache_data(max_entries=12,show_spinner='방문일별 코호트를 계산하는 중입니다…')
def cached_visit_cohorts(path,version,start,end,key=None,entity='전체',root=None,category=None,grain='일별',cohort_end=None):
    events=scope_events(retention_events(path,version),root,category)
    return visit_cohorts(events,key,entity,start,end,grain,cohort_end)
