#!/usr/bin/env python3
"""
割安小型株スクリーナー v2
"""
import threading, time, os, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from io import BytesIO
from datetime import datetime
import requests, pandas as pd, yfinance as yf

BG="#1a1a2e";BG2="#16213e";ACCENT="#e94560";WHITE="#ffffff"
GRAY="#cccccc";GREEN="#4ecca3";YELLOW="#ffd460";ORANGE="#ff9a3c"
SECTOR_JP={"Basic Materials":"素材","Communication Services":"通信サービス","Consumer Cyclical":"一般消費財","Consumer Defensive":"生活必需品","Energy":"エネルギー","Financial Services":"金融","Healthcare":"ヘルスケア","Industrials":"資本財・サービス","Real Estate":"不動産","Technology":"テクノロジー","Utilities":"公益事業"}
class ScreenerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("割安小型株スクリーナー v2")
        self.geometry("1100x780")
        self.configure(bg=BG)
        self.resizable(True,True)
        self._running=False;self._paused=False;self._stop_flag=False
        self._results=pd.DataFrame()
        self._build_ui()
    def _btn(self,parent,text,bg,fg,cmd,disabled=False):
        b=tk.Button(parent,text=text,bg=bg,fg=fg,activebackground=bg,activeforeground=fg,
                    disabledforeground=GRAY,font=("Helvetica",11,"bold"),relief="flat",
                    cursor="hand2",command=cmd,state="disabled" if disabled else "normal")
        b.pack(fill="x",padx=16,pady=4,ipady=8)
        return b
    def _build_ui(self):
        hdr=tk.Frame(self,bg=ACCENT,height=56);hdr.pack(fill="x");hdr.pack_propagate(False)
        tk.Label(hdr,text="割安小型株スクリーナー（清原さん流）",bg=ACCENT,fg=WHITE,font=("Helvetica",16,"bold")).pack(side="left",padx=20,pady=12)
        main=tk.Frame(self,bg=BG);main.pack(fill="both",expand=True,padx=16,pady=12)
        left=tk.Frame(main,bg=BG2,width=240);left.pack(side="left",fill="y",padx=(0,12));left.pack_propagate(False)
        tk.Label(left,text="スクリーニング条件",bg=BG2,fg=GREEN,font=("Helvetica",12,"bold")).pack(anchor="w",padx=16,pady=(16,8))
        self.vars={}
        for label,key,default in [("PER上限","per_max","10.0"),("PBR上限","pbr_max","1.0"),("NC比率下限","nc_min","1.0"),("時価総額上限(億)","mktcap_max","500"),("スリープ(秒)","sleep","0.5"),("テスト銘柄数(0=全件)","max_n","0")]:
            f=tk.Frame(left,bg=BG2);f.pack(fill="x",padx=16,pady=4)
            tk.Label(f,text=label,bg=BG2,fg=GRAY,font=("Helvetica",10)).pack(anchor="w")
            v=tk.StringVar(value=default);self.vars[key]=v
            tk.Entry(f,textvariable=v,bg="#0f3460",fg=WHITE,insertbackground=WHITE,relief="flat",font=("Helvetica",11),width=14).pack(fill="x",ipady=4)
        self.btn_run=tk.Button(left,text="▶ スクリーニング開始",bg=ACCENT,fg=WHITE,activebackground=ACCENT,activeforeground=WHITE,font=("Helvetica",12,"bold"),relief="flat",cursor="hand2",command=self._start_screening)
        self.btn_run.pack(fill="x",padx=16,pady=(20,4),ipady=10)
        self.btn_pause=self._btn(left,"|| 一時停止",ORANGE,WHITE,self._toggle_pause,disabled=True)
        self.btn_stop=self._btn(left,"■ 中止","#cc4444",WHITE,self._stop_screening,disabled=True)
        self.btn_mid_save=self._btn(left,"途中経過を保存",BG2,YELLOW,self._save_csv,disabled=True)
        self.btn_save=self._btn(left,"CSV を保存",BG2,GREEN,self._save_csv,disabled=True)
        style=ttk.Style(self);style.theme_use("default")
        style.configure("c.Horizontal.TProgressbar",troughcolor=BG,background=GREEN,thickness=8)
        self.progress=ttk.Progressbar(left,style="c.Horizontal.TProgressbar",orient="horizontal",mode="determinate")
        self.progress.pack(fill="x",padx=16,pady=(12,4))
        self.lbl_progress=tk.Label(left,text="待機中",bg=BG2,fg=GRAY,font=("Helvetica",9));self.lbl_progress.pack(anchor="w",padx=16)
        self.lbl_hits=tk.Label(left,text="ヒット: 0件",bg=BG2,fg=GREEN,font=("Helvetica",11,"bold"));self.lbl_hits.pack(anchor="w",padx=16,pady=(4,0))
        right=tk.Frame(main,bg=BG);right.pack(side="left",fill="both",expand=True)
        nb_style=ttk.Style();nb_style.configure("TNotebook",background=BG,borderwidth=0)
        nb_style.configure("TNotebook.Tab",background=BG2,foreground=GRAY,padding=[12,6],font=("Helvetica",10))
        nb_style.map("TNotebook.Tab",background=[("selected",ACCENT)],foreground=[("selected",WHITE)])
        self.nb=ttk.Notebook(right,style="TNotebook");self.nb.pack(fill="both",expand=True)
        self.tab_all=tk.Frame(self.nb,bg=BG);self.nb.add(self.tab_all,text="  全銘柄一覧  ");self.tree_all=self._make_tree(self.tab_all)
        self.tab_sec=tk.Frame(self.nb,bg=BG);self.nb.add(self.tab_sec,text="  セクター別  ");self.tree_sec=self._make_tree(self.tab_sec)
        self.log=tk.Text(right,height=5,bg="#0a0a1a",fg=GRAY,font=("Menlo",9),relief="flat",state="disabled");self.log.pack(fill="x",pady=(8,0))
    def _make_tree(self,parent):
        cols=("コード","銘柄名","セクター","株価","時価総額","PER","PBR","NC比率","配当利回り")
        frame=tk.Frame(parent,bg=BG);frame.pack(fill="both",expand=True)
        vsb=ttk.Scrollbar(frame,orient="vertical");vsb.pack(side="right",fill="y")
        hsb=ttk.Scrollbar(frame,orient="horizontal");hsb.pack(side="bottom",fill="x")
        style=ttk.Style()
        style.configure("Treeview",background="#0f3460",foreground=WHITE,fieldbackground="#0f3460",rowheight=26,font=("Helvetica",10))
        style.configure("Treeview.Heading",background=BG2,foreground=GREEN,font=("Helvetica",10,"bold"),relief="flat")
        style.map("Treeview",background=[("selected",ACCENT)])
        tree=ttk.Treeview(frame,columns=cols,show="headings",yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        for col,w in zip(cols,[60,160,120,70,80,55,55,70,80]):
            tree.heading(col,text=col);tree.column(col,width=w,anchor="e" if col not in("銘柄名","セクター") else "w")
        vsb.config(command=tree.yview);hsb.config(command=tree.xview);tree.pack(fill="both",expand=True)
        return tree
    def _log(self,msg):
        self.log.config(state="normal");self.log.insert("end",f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n");self.log.see("end");self.log.config(state="disabled")
    def _start_screening(self):
        if self._running:return
        self._running=True;self._paused=False;self._stop_flag=False;self._results=pd.DataFrame()
        self.btn_run.config(state="disabled",text="スキャン中...",bg="#555555")
        self.btn_pause.config(state="normal",bg=ORANGE,fg=WHITE)
        self.btn_stop.config(state="normal")
        self.btn_mid_save.config(state="normal")
        self.btn_save.config(state="disabled")
        self.lbl_hits.config(text="ヒット: 0件")
        for tree in(self.tree_all,self.tree_sec):
            for item in tree.get_children():tree.delete(item)
        threading.Thread(target=self._run_screening,daemon=True).start()
    def _toggle_pause(self):
        if not self._running:return
        self._paused=not self._paused
        if self._paused:
            self.btn_pause.config(text="▶ 再開",bg=GREEN,fg=BG);self.lbl_progress.config(text="一時停止中...");self._log("一時停止しました")
        else:
            self.btn_pause.config(text="|| 一時停止",bg=ORANGE,fg=WHITE);self._log("再開しました")
    def _stop_screening(self):
        if not self._running:return
        if messagebox.askyesno("中止確認","スキャンを中止しますか？\n（途中までの結果は保持されます）"):
            self._stop_flag=True;self._paused=False;self._log("中止しました")
    def _run_screening(self):
        try:
            per_max=float(self.vars["per_max"].get());pbr_max=float(self.vars["pbr_max"].get())
            nc_min=float(self.vars["nc_min"].get());mktcap_max=float(self.vars["mktcap_max"].get())
            sleep_sec=float(self.vars["sleep"].get());max_n=int(self.vars["max_n"].get())
            self._log("JPX上場銘柄リストを取得中...")
            url="https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
            resp=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=30);resp.raise_for_status()
            df_all=pd.read_excel(BytesIO(resp.content),header=0);df_all.columns=df_all.columns.str.strip()
            code_col=[c for c in df_all.columns if "コード" in c][0]
            name_col=[c for c in df_all.columns if "銘柄名" in c or "会社名" in c][0]
            tickers=df_all[[code_col,name_col]].copy();tickers.columns=["code","name"]
            tickers["code"]=tickers["code"].astype(str).str.zfill(4)
            if max_n>0:tickers=tickers.head(max_n)
            total=len(tickers);self._log(f"{total:,}銘柄をスキャン開始")
            results=[]
            for i,(_,row) in enumerate(tickers.iterrows()):
                if self._stop_flag:break
                while self._paused:time.sleep(0.3)
                pct=int((i+1)/total*100);self.progress["value"]=pct
                self.lbl_progress.config(text=f"{i+1:,} / {total:,}（{pct}%）");self.update_idletasks()
                sym=row["code"]+".T"
                try:
                    t=yf.Ticker(sym);fi=t.fast_info
                    mktcap=getattr(fi,"market_cap",None)
                    if not mktcap or mktcap<=0:continue
                    mktcap_oku=mktcap/1e8
                    if mktcap_oku>mktcap_max:continue
                    info=t.info;per=info.get("trailingPE",None);pbr=info.get("priceToBook",None)
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
                    price=getattr(fi,"last_price",None);div_y=info.get("dividendYield",None)
                    sec_en=info.get("sector","");sector=SECTOR_JP.get(sec_en,sec_en) if sec_en else "—"
                    div_str=f"{round(div_y*100,2)}%" if div_y and div_y<1 else(f"{round(div_y,2)}%" if div_y else "—")
                    r={"証券コード":row["code"],"銘柄名":row["name"],"セクター":sector,"株価":round(price,0) if price else None,"時価総額(億円)":round(mktcap_oku,1),"PER":round(per,2),"PBR":round(pbr,2),"NC比率":round(nc_ratio,2),"配当利回り":div_str}
                    results.append(r);self._results=pd.DataFrame(results)
                    self.after(0,self._insert_row,r,len(results));self._log(f"ヒット: {row['name']}（{row['code']}）NC比率={round(nc_ratio,2)}")
                except Exception:pass
                time.sleep(sleep_sec)
            self._results=pd.DataFrame(results);self.after(0,self._on_done)
        except Exception as e:
            self._log(f"エラー: {e}");self.after(0,self._reset_btn)
    def _insert_row(self,r,hit_count):
        vals=(r["証券コード"],r["銘柄名"],r["セクター"],r["株価"],r["時価総額(億円)"],r["PER"],r["PBR"],r["NC比率"],r["配当利回り"])
        self.tree_all.insert("","end",values=vals);self.lbl_hits.config(text=f"ヒット: {hit_count}件")
    def _on_done(self):
        count=len(self._results);stopped="（中止）" if self._stop_flag else ""
        self._log(f"完了{stopped}！条件を満たした銘柄: {count}件")
        self._update_sector_tab();self.btn_save.config(state="normal",bg=GREEN,fg=BG);self._reset_btn()
        os.system("afplay /System/Library/Sounds/Glass.aiff &")
    def _update_sector_tab(self):
        for item in self.tree_sec.get_children():self.tree_sec.delete(item)
        if self._results.empty:return
        df=self._results.sort_values(["セクター","NC比率"],ascending=[True,False]);current_sector=None
        for _,r in df.iterrows():
            if r["セクター"]!=current_sector:
                current_sector=r["セクター"]
                self.tree_sec.insert("","end",values=("──",f"[ {current_sector} ]","","","","","","",""),tags=("header",))
                self.tree_sec.tag_configure("header",foreground=YELLOW,background=BG2)
            self.tree_sec.insert("","end",values=(r["証券コード"],r["銘柄名"],r["セクター"],r["株価"],r["時価総額(億円)"],r["PER"],r["PBR"],r["NC比率"],r["配当利回り"]))
    def _reset_btn(self):
        self._running=False;self._paused=False;self._stop_flag=False
        self.btn_run.config(state="normal",text="▶ スクリーニング開始",bg=ACCENT,fg=WHITE)
        self.btn_pause.config(state="disabled",text="|| 一時停止",bg=ORANGE,fg=WHITE)
        self.btn_stop.config(state="disabled")
        self.btn_mid_save.config(state="disabled")
    def _save_csv(self):
        if self._results.empty:messagebox.showwarning("保存","データがありません");return
        now=datetime.now().strftime("%Y%m%d_%H%M")
        path=filedialog.asksaveasfilename(defaultextension=".csv",initialfile=f"screening_{now}.csv",filetypes=[("CSV","*.csv")])
        if path:
            self._results.sort_values("NC比率",ascending=False).to_csv(path,index=False,encoding="utf-8-sig")
            self._log(f"保存しました: {path}");messagebox.showinfo("保存完了",f"保存しました！\n{path}")
if __name__=="__main__":
    app=ScreenerApp();app.mainloop()
