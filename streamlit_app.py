import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
from io import BytesIO

SECTOR_JP={"Basic Materials":"素材","Communication Services":"通信サービス","Consumer Cyclical":"一般消費財","Consumer Defensive":"生活必需品","Energy":"エネルギー","Financial Services":"金融","Healthcare":"ヘルスケア","Industrials":"資本財・サービス","Real Estate":"不動産","Technology":"テクノロジー","Utilities":"公益事業"}

st.set_page_config(page_title="割安小型株スクリーナー",page_icon="📈",layout="wide")
st.title("📈 割安小型株スクリーナー（清原さん流）")
st.caption("条件: PER低・PBR低・NC比率高・時価総額500億円以下")

with st.sidebar:
    st.header("⚙️ スクリーニング条件")
    per_max=st.number_input("PER上限",value=10.0,step=0.5)
    pbr_max=st.number_input("PBR上限",value=1.0,step=0.1)
    nc_min=st.number_input("NC比率下限",value=1.0,step=0.1)
    mktcap_max=st.number_input("時価総額上限(億円)",value=500,step=50)
    max_n=st.number_input("テスト銘柄数(0=全件)",value=100,step=50)
    run=st.button("▶ スクリーニング開始",type="primary",use_container_width=True)

if run:
    with st.spinner("JPX銘柄リストを取得中..."):
        url="https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        resp=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=30)
        df_all=pd.read_excel(BytesIO(resp.content),header=0)
        df_all.columns=df_all.columns.str.strip()
        code_col=[c for c in df_all.columns if "コード" in c][0]
        name_col=[c for c in df_all.columns if "銘柄名" in c or "会社名" in c][0]
        tickers=df_all[[code_col,name_col]].copy()
        tickers.columns=["code","name"]
        tickers["code"]=tickers["code"].astype(str).str.zfill(4)
        if max_n>0:tickers=tickers.head(int(max_n))

    st.info(f"{len(tickers):,}銘柄をスキャン中...（時間がかかります）")
    progress=st.progress(0)
    status=st.empty()
    results=[]

    for i,(_,row) in enumerate(tickers.iterrows()):
        progress.progress((i+1)/len(tickers))
        status.text(f"{i+1}/{len(tickers)} スキャン中... ヒット: {len(results)}件")
        sym=row["code"]+".T"
        try:
            t=yf.Ticker(sym);fi=t.fast_info
            mktcap=getattr(fi,"market_cap",None)
            if not mktcap or mktcap<=0:continue
            mktcap_oku=mktcap/1e8
            if mktcap_oku>mktcap_max:continue
            info=t.info
            per=info.get("trailingPE",None);pbr=info.get("priceToBook",None)
            if not per or per<=0 or per>per_max:continue
            if not pbr or pbr<=0 or pbr>pbr_max:continue
            bs=t.balance_sheet
            if bs is None or bs.empty:continue
            latest=bs.iloc[:,0];ca=tl=None
            for k in["Current Assets","Total Current Assets"]:
                if k in latest.index:ca=latest[k];break
            for k in["Total Liabilities Net Minority Interest","Total Liabilities"]:
                if k in latest.index:tl=latest[k];break
            if ca is None or tl is None or pd.isna(ca) or pd.isna(tl):continue
            if ca<=tl:continue
            nc=ca-tl;nc_ratio=nc/mktcap
            if nc_ratio<nc_min:continue
            price=getattr(fi,"last_price",None)
            div_y=info.get("dividendYield",None)
            sec_en=info.get("sector","")
            sector=SECTOR_JP.get(sec_en,sec_en) if sec_en else "—"
            div_str=f"{round(div_y*100,2)}%" if div_y and div_y<1 else(f"{round(div_y,2)}%" if div_y else "—")
            results.append({"証券コード":row["code"],"銘柄名":row["name"],"セクター":sector,"株価":round(price,0) if price else None,"時価総額(億円)":round(mktcap_oku,1),"PER":round(per,2),"PBR":round(pbr,2),"NC比率":round(nc_ratio,2),"配当利回り":div_str})
        except:pass
        time.sleep(0.3)

    progress.progress(1.0)
    status.text(f"完了！ヒット: {len(results)}件")

    if results:
        df=pd.DataFrame(results).sort_values("NC比率",ascending=False)
        st.success(f"🎯 条件を満たした銘柄: {len(df)}件")
        tab1,tab2=st.tabs(["📋 全銘柄一覧","📂 セクター別"])
        with tab1:
            st.dataframe(df,use_container_width=True,hide_index=True)
            csv=df.to_csv(index=False,encoding="utf-8-sig")
            st.download_button("💾 CSVダウンロード",csv,"screening_result.csv","text/csv",use_container_width=True)
        with tab2:
            for sector,group in df.groupby("セクター"):
                st.subheader(f"📂 {sector}（{len(group)}社）")
                st.dataframe(group,use_container_width=True,hide_index=True)
    else:
        st.warning("条件を満たす銘柄が見つかりませんでした")
