"""송탄고 급식의 메뉴 연관 규칙 탐색기."""

from collections import Counter
from itertools import combinations
import re

import pandas as pd
import plotly.express as px
import streamlit as st


DATA_URL = "https://raw.githubusercontent.com/it-teacher-go/data-share-/main/songtan_meals_184.csv"

st.set_page_config(page_title="급식 규칙 찾기", page_icon="🍱", layout="wide")
st.title("🍱 급식 규칙 찾기")
st.caption("송탄고 중식 184일 · 함께 등장한 메뉴에서 연관 규칙을 찾아봅니다.")


def clean_menu(value: str) -> str:
    """메뉴의 괄호 및 괄호 안 정보(알레르기 번호 등)를 제거합니다."""
    value = str(value).strip()
    # 괄호 종류와 중첩된 괄호를 모두 반복적으로 처리합니다.
    pattern = r"\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}|（[^（）]*）"
    while re.search(pattern, value):
        value = re.sub(pattern, "", value)
    return " ".join(value.split())


@st.cache_data(ttl=3600)
def load_baskets():
    df = pd.read_csv(DATA_URL, encoding="utf-8", dtype=str)
    required = {"날짜", "식사", "메뉴"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV에 필요한 열이 없습니다: {', '.join(sorted(required - set(df.columns)))}")

    baskets = []
    for menu_string in df["메뉴"].fillna(""):
        menus = {clean_menu(item) for item in menu_string.split("|")}
        menus.discard("")
        if menus:
            baskets.append(menus)
    return baskets


@st.cache_data
def calculate_rules(baskets_as_tuples):
    baskets = [set(basket) for basket in baskets_as_tuples]
    n = len(baskets)
    menu_counts = Counter(menu for basket in baskets for menu in basket)
    pair_counts = Counter(
        pair for basket in baskets for pair in combinations(sorted(basket), 2)
    )

    records = []
    for (a, b), together in pair_counts.items():
        for condition, result in ((a, b), (b, a)):
            support = together / n
            confidence = together / menu_counts[condition]
            lift = confidence / (menu_counts[result] / n)
            records.append({
                "조건": condition,
                "결과": result,
                "동시": together,
                "지지도": support,
                "신뢰도": confidence,
                "향상도": lift,
            })

    columns = ["조건", "결과", "동시", "지지도", "신뢰도", "향상도"]
    return pd.DataFrame(records, columns=columns), len(menu_counts), len(pair_counts)


try:
    baskets = load_baskets()
except Exception as exc:
    st.error("급식 CSV를 불러오지 못했습니다. 주소, 파일 공개 설정, 열 이름을 확인해 주세요.")
    st.exception(exc)
    st.stop()

if not baskets:
    st.warning("분석할 메뉴가 없습니다.")
    st.stop()

rules, menu_count, pair_count = calculate_rules(
    tuple(tuple(sorted(basket)) for basket in baskets)
)

metric_cols = st.columns(3)
metric_cols[0].metric("급식 일수", f"{len(baskets):,}일")
metric_cols[1].metric("메뉴 종류 수", f"{menu_count:,}종")
metric_cols[2].metric("함께 나온 메뉴 쌍", f"{pair_count:,}쌍")

st.divider()
filter_col, sort_col = st.columns([2, 1])
with filter_col:
    all_menus = sorted({menu for basket in baskets for menu in basket})
    chosen = st.selectbox("메뉴 선택", ["전체 메뉴"] + all_menus)
with sort_col:
    sort_name = st.selectbox("정렬 기준", ["향상도 순", "신뢰도 순", "동시 순"])

if chosen != "전체 메뉴":
    rules = rules[(rules["조건"] == chosen) | (rules["결과"] == chosen)].copy()

sort_key = {"향상도 순": "향상도", "신뢰도 순": "신뢰도", "동시 순": "동시"}[sort_name]
rules = rules.sort_values(
    [sort_key, "동시", "조건", "결과"],
    ascending=[False, False, True, True],
    kind="stable",
).reset_index(drop=True)

st.subheader(f"연관 규칙 ({len(rules):,}개)")
st.dataframe(
    rules,
    hide_index=True,
    use_container_width=True,
    column_config={
        "동시": st.column_config.NumberColumn("동시", help="두 메뉴가 함께 등장한 급식 일수", format="%d일"),
        "지지도": st.column_config.NumberColumn("지지도", help="동시 등장 일수 ÷ 전체 급식 일수", format="%.2f"),
        "신뢰도": st.column_config.NumberColumn("신뢰도", help="동시 등장 일수 ÷ 조건 메뉴 등장 일수", format="%.2f"),
        "향상도": st.column_config.NumberColumn("향상도", help="신뢰도 ÷ 결과 메뉴 등장 비율", format="%.2f"),
    },
)

st.subheader("📊 향상도 상위 10개 규칙")
if rules.empty:
    st.info("선택한 메뉴에 해당하는 규칙이 없습니다.")
else:
    top10 = rules.sort_values(
        ["향상도", "동시", "조건", "결과"],
        ascending=[False, False, True, True],
    ).head(10).copy()
    top10["규칙"] = top10["조건"] + " → " + top10["결과"]
    fig = px.bar(
        top10.sort_values("향상도"),
        x="향상도",
        y="규칙",
        orientation="h",
        hover_data={"동시": True, "지지도": ":.3f", "신뢰도": ":.3f", "향상도": ":.2f"},
        labels={"규칙": "메뉴 규칙", "향상도": "향상도 (Lift)"},
    )
    fig.update_layout(height=max(420, len(top10) * 42), margin=dict(l=15, r=15, t=15, b=15))
    st.plotly_chart(fig, use_container_width=True)

with st.expander("지표 해석 방법"):
    st.markdown(
        """
        - **동시**: 두 메뉴가 같은 날 나온 횟수입니다.
        - **지지도**: 두 메뉴가 함께 나온 날 ÷ 전체 급식 일수입니다.
        - **신뢰도**: 조건 메뉴가 나온 날 중 결과 메뉴도 나온 비율입니다.
        - **향상도**: 신뢰도 ÷ 결과 메뉴가 나온 전체 비율입니다.
          1보다 크면 두 메뉴가 우연한 등장 비율보다 더 자주 함께 관찰된다는 뜻입니다.

        한 쌍의 규칙은 `A → B`, `B → A`를 모두 포함합니다. 두 방향의 **지지도와 향상도는 같고**, 신뢰도는 다를 수 있습니다.
        향상도가 높더라도 동시 등장 횟수가 작다면 해석에 주의하세요.
        """
    )
