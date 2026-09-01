import json, statistics, urllib.parse, urllib.request, time, random, subprocess, re, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
SINA = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData"
CURL = shutil.which("curl.exe") or shutil.which("curl")
WATCH = [
    ("芯片ETF易方达", "516350", "1", "芯片ETF"), ("科创新材料ETF博时", "588010", "1", "科创ETF"),
    ("科创100ETF华夏", "588800", "1", "科创ETF"), ("农业银行", "601288", "1", "银行"),
    ("快克智能", "603203", "1", "个股"), ("格力电器", "000651", "0", "个股"),
    ("福晶科技", "002222", "0", "个股"), ("中天精装", "002989", "0", "个股"),
    ("机器人ETF易方达", "159530", "0", "机器人ETF"), ("长芯博创", "300548", "0", "个股"),
    ("罗博特科", "300757", "0", "个股")]

def get(name, code, market, group, limit=800):
    params={"secid":f"{market}.{code}","klt":"101","fqt":"1","lmt":str(limit),"end":"20500101",
            "fields1":"f1,f2,f3,f4,f5,f6","fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}
    url=API+"?"+urllib.parse.urlencode(params); last_error=None; obj=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://quote.eastmoney.com/"})
            with urllib.request.urlopen(req,timeout=25) as resp: obj=json.loads(resp.read().decode("utf-8"))
            if obj.get("data") and obj["data"].get("klines"): break
            raise RuntimeError("接口返回空行情")
        except Exception as exc:
            last_error=exc
            if attempt==1: break
            time.sleep(.8+random.random())
    if obj is None or not obj.get("data") or not obj["data"].get("klines"):
        if CURL:
            curl=subprocess.run([CURL,"-sS","-L","--retry","1","--connect-timeout","8","--max-time","18","-A","Mozilla/5.0",url],capture_output=True,text=True,encoding="utf-8",timeout=40)
            if curl.returncode==0:
                try: obj=json.loads(curl.stdout)
                except Exception: obj=None
    if obj is None or not obj.get("data") or not obj["data"].get("klines"):
        symbol=("sh" if market=="1" else "sz")+code
        su=SINA+"?"+urllib.parse.urlencode({"symbol":symbol,"scale":"240","ma":"no","datalen":str(limit)})
        sina_text=""; sina_error=None
        try:
            req=urllib.request.Request(su,headers={"User-Agent":"Mozilla/5.0","Referer":"https://finance.sina.com.cn/"})
            with urllib.request.urlopen(req,timeout=25) as resp: sina_text=resp.read().decode("utf-8")
        except Exception as exc: sina_error=exc
        if not sina_text and CURL:
            curl_args=[CURL,"-sS","-L","--retry","2","--connect-timeout","8","--max-time","20","-A","Mozilla/5.0","-e","https://finance.sina.com.cn/",su]
            if "Windows" in __import__("platform").system(): curl_args.insert(1,"--ssl-no-revoke")
            curl=subprocess.run(curl_args,capture_output=True,text=True,encoding="utf-8",timeout=60); sina_text=curl.stdout
            if curl.returncode: sina_error=curl.stderr.strip()
        match=re.search(r"\(\s*(\[.*\])\s*\);",sina_text,re.S)
        if not match: raise RuntimeError(str(sina_error or last_error))
        rows=[]; previous=None
        for x in json.loads(match.group(1)):
            close=float(x["close"]); change=(close/previous-1)*100 if previous else 0
            rows.append({"date":x["day"][:10],"open":float(x["open"]),"close":close,"high":float(x["high"]),"low":float(x["low"]),"volume":float(x["volume"]),"pct":change}); previous=close
        return {"name":name,"code":code,"group":group,"dataSource":"新浪财经日线（备用）","rows":rows}
    rows=[]
    for line in obj["data"]["klines"]:
        x=line.split(","); rows.append({"date":x[0],"open":float(x[1]),"close":float(x[2]),"high":float(x[3]),"low":float(x[4]),"volume":float(x[5]),"pct":float(x[8])})
    return {"name":name,"code":code,"group":group,"dataSource":"东方财富日线（主）","rows":rows}

def sma(vals,n,end=None):
    end=len(vals) if end is None else end
    return sum(vals[end-n:end])/n if end>=n else None
def ema(vals,n):
    alpha=2/(n+1); out=[]
    for value in vals: out.append(value if not out else alpha*value+(1-alpha)*out[-1])
    return out
def change_pct(a,b): return (a/b-1)*100 if b else 0
def fmt(value,digits=2): return None if value is None else round(value,digits)

def aggregate(rows,period):
    buckets=[]
    for row in rows:
        day=datetime.strptime(row["date"],"%Y-%m-%d")
        key=(day.isocalendar().year,day.isocalendar().week) if period=="week" else (day.year,day.month)
        if not buckets or buckets[-1]["key"]!=key:
            buckets.append({"key":key,"date":row["date"],"open":row["open"],"close":row["close"],"high":row["high"],"low":row["low"],"volume":row["volume"]})
        else:
            bar=buckets[-1]; bar.update(date=row["date"],close=row["close"],high=max(bar["high"],row["high"]),low=min(bar["low"],row["low"]),volume=bar["volume"]+row["volume"])
    previous=None; result=[]
    for bar in buckets:
        bar.pop("key",None); bar["pct"]=change_pct(bar["close"],previous) if previous else 0; previous=bar["close"]; result.append(bar)
    return result

def bbi_series(closes):
    out=[]
    for end in range(1,len(closes)+1):
        parts=[sma(closes,n,end) for n in (3,6,12,24)]
        out.append(statistics.mean(parts) if all(v is not None for v in parts) else None)
    return out

def kdj_series(rows):
    k=d=50.0; js=[]
    for i,row in enumerate(rows):
        window=rows[max(0,i-8):i+1]; high=max(x["high"] for x in window); low=min(x["low"] for x in window)
        rsv=(row["close"]-low)/(high-low)*100 if high!=low else 50; k=2*k/3+rsv/3; d=2*d/3+k/3; js.append(3*k-2*d)
    return js
def tail_streak(values,predicate):
    count=0
    for value in reversed(values):
        if predicate(value): count+=1
        else: break
    return count

def find_n(rows,span=2,lookback=130):
    if len(rows)<12: return {"phase":"样本不足","kind":"none","markers":[]}
    offset=max(0,len(rows)-lookback); sample=rows[offset:]; pivots=[]
    for i in range(span,len(sample)-span):
        lows=[x["low"] for x in sample[i-span:i+span+1]]; highs=[x["high"] for x in sample[i-span:i+span+1]]; candidate=None
        if sample[i]["low"]==min(lows): candidate={"type":"L","i":offset+i,"price":sample[i]["low"],"date":sample[i]["date"]}
        if sample[i]["high"]==max(highs) and (candidate is None or sample[i]["high"]-min(lows)>max(highs)-sample[i]["low"]): candidate={"type":"H","i":offset+i,"price":sample[i]["high"],"date":sample[i]["date"]}
        if not candidate: continue
        if pivots and pivots[-1]["type"]==candidate["type"]:
            better=candidate["price"]<pivots[-1]["price"] if candidate["type"]=="L" else candidate["price"]>pivots[-1]["price"]
            if better: pivots[-1]=candidate
        else: pivots.append(candidate)
    close=rows[-1]["close"]
    for i in range(len(pivots)-3,-1,-1):
        a,b,c=pivots[i:i+3]
        if (a["type"],b["type"],c["type"])==("L","H","L") and c["price"]>a["price"]:
            rise=b["price"]-a["price"]; retrace=(b["price"]-c["price"])/rise if rise>0 else 9
            if .08<=retrace<=.65:
                vol_high=statistics.mean(x["volume"] for x in rows[max(0,b["i"]-2):b["i"]+3]); vol_low=statistics.mean(x["volume"] for x in rows[max(0,c["i"]-2):c["i"]+3]); volume_ratio=vol_low/vol_high if vol_high else None
                phase="上升N已突破（N+1后）" if close>b["price"] else "上升N回踩/等待N+1" if close>=c["price"]*.97 else "上升N结构受损"
                return {"phase":phase,"kind":"up","l1":fmt(a["price"],3),"h1":fmt(b["price"],3),"l2":fmt(c["price"],3),"retrace":fmt(retrace*100,1),"volumeRatio":fmt(volume_ratio,2),"markers":[{"d":x["date"],"p":fmt(x["price"],3),"t":x["type"]} for x in (a,b,c)]}
        if (a["type"],b["type"],c["type"])==("H","L","H") and c["price"]<a["price"]: return {"phase":"下降N/反弹未转强","kind":"down","markers":[]}
    return {"phase":"未识别出清晰N形","kind":"none","markers":[]}

def timeframe(rows,label,span):
    closes=[x["close"] for x in rows]; bbi_values=bbi_series(closes); js=kdj_series(rows); e12,e26=ema(closes,12),ema(closes,26); dif=[a-b for a,b in zip(e12,e26)]; dea=ema(dif,9); hist=[2*(a-b) for a,b in zip(dif,dea)]; bbi=bbi_values[-1]
    base=next((bbi_values[i] for i in range(max(0,len(bbi_values)-4),-1,-1) if bbi_values[i] is not None),bbi)
    return {"label":label,"close":fmt(closes[-1],3),"bbi":fmt(bbi,3),"aboveBbi":bool(bbi and closes[-1]>=bbi),"bbiSlope":"向上" if bbi and base and bbi>base else "向下" if bbi and base and bbi<base else "走平","j":fmt(js[-1],1),"jPrev":fmt(js[-2],1),"jNegStreak":tail_streak(js,lambda x:x<0),"j100Streak":tail_streak(js,lambda x:x>100),"macdHist":fmt(hist[-1],4),"macdImproving":hist[-1]>hist[-2],"n":find_n(rows,span=span,lookback=130 if label=="日线" else 80)}

def analyze(item):
    rows=item.pop("rows")
    if len(rows)<80: raise RuntimeError("历史数据不足，无法计算多周期规则")
    closes=[x["close"] for x in rows]; volumes=[x["volume"] for x in rows]; last,previous=rows[-1],rows[-2]
    mas={str(n):sma(closes,n) for n in (5,8,10,13,21,34,55,60)}; daily_bbis=bbi_series(closes)
    daily=timeframe(rows,"日线",2); weekly=timeframe(aggregate(rows,"week"),"周线",1); monthly=timeframe(aggregate(rows,"month"),"月线",1)
    vol10=sma(volumes,10); vol_ratio=last["volume"]/vol10 if vol10 else 1; hi20=max(x["high"] for x in rows[-20:]); low20=min(x["low"] for x in rows[-20:]); pos20=(last["close"]-low20)/(hi20-low20)*100 if hi20!=low20 else 50
    previous_bbi=daily_bbis[-2]; previous_ma60=sma(closes,60,len(closes)-1); cross_up_bbi=previous["close"]<=previous_bbi and last["close"]>daily["bbi"]; cross_down_bbi=previous["close"]>=previous_bbi and last["close"]<daily["bbi"]; cross_down_ma60=previous["close"]>=previous_ma60 and last["close"]<mas["60"]
    body=abs(last["close"]-last["open"]); lower_shadow=min(last["open"],last["close"])-last["low"]; upper_shadow=last["high"]-max(last["open"],last["close"]); candle_range=max(last["high"]-last["low"],.000001)
    stop_candle=lower_shadow>=max(body*1.5,candle_range*.35); bullish_confirm=last["close"]>last["open"] and last["pct"]>=2 and vol_ratio>=1.25; high_volume_stall=pos20>=75 and vol_ratio>=1.8 and last["pct"]<3 and (last["pct"]<=1 or upper_shadow>body); top_bear=pos20>=70 and last["pct"]<=-3 and vol_ratio>=1.5
    weekly_safe=weekly["aboveBbi"] and weekly["bbiSlope"]!="向下"; month_safe=monthly["aboveBbi"] and monthly["bbiSlope"]!="向下"; n=daily["n"]; n_contracted=n.get("volumeRatio") is not None and n["volumeRatio"]<=.65; low_j=daily["j"]<13; is_etf="ETF" in item["name"]; redline_both=last["close"]<daily["bbi"] and last["close"]<mas["60"]
    reasons=[f"月线：{monthly['n']['phase']}；BBI{monthly['bbiSlope']}，收盘{'在线上' if monthly['aboveBbi'] else '在线下'}",f"周线：{weekly['n']['phase']}；BBI{weekly['bbiSlope']}，收盘{'在线上' if weekly['aboveBbi'] else '在线下'}",f"日线：{n['phase']}；J={daily['j']}（负值连续{daily['jNegStreak']}天，100以上连续{daily['j100Streak']}天）"]
    if n.get("retrace") is not None: reasons.append(f"日线N回撤约{n['retrace']}%，回踩量/前高量约{n.get('volumeRatio')}倍")
    reasons.append(f"当日量/10日均量={fmt(vol_ratio,2)}倍，{'缩量' if vol_ratio<.8 else '放量' if vol_ratio>1.25 else '量能普通'}")
    if stop_candle: reasons.append("出现较明显下影线，具备止跌观察特征")
    if bullish_confirm: reasons.append("出现放量中阳线，具备N+1确认特征")
    risks=[]
    if not weekly_safe: risks.append("周线尚未同时满足站上BBI且BBI不向下，买点安全垫不足")
    if cross_down_bbi: risks.append("今日收盘刚跌破日线BBI")
    if cross_down_ma60: risks.append("今日收盘刚跌破MA60")
    if daily["j100Streak"]>=3: risks.append("J值连续3天高于100，触发材料中的分批止盈信号")
    if high_volume_stall: risks.append("高位放量但涨幅不足，符合放量滞涨警报")
    if top_bear: risks.append("相对高位放量大跌，符合明确离场警报")
    if redline_both: risks.append("收盘同时位于日线BBI和MA60下方，处于趋势红线区")
    if top_bear: held_action,unheld_action,level="减仓1/2至退出观察","不买，等重新站回趋势线","红线"
    elif redline_both: held_action,unheld_action,level="减仓1/2；两周不收回则退出","不抄底，等待周日线修复","红线"
    elif cross_down_bbi or cross_down_ma60: held_action,unheld_action,level="先减1/3；次日不收回再降仓","暂不买，观察能否快速收回","减仓"
    elif daily["j100Streak"]>=3 or high_volume_stall: held_action,unheld_action,level="卖出1/3保护利润","不追高，等缩量回踩","止盈"
    elif is_etf and weekly_safe and cross_up_bbi and last["pct"]<7: held_action,unheld_action,level="持有，BBI作防守","可考虑试仓1/3","确认买点"
    elif not is_etf and weekly_safe and n["kind"]=="up" and n["phase"].startswith("上升N已突破") and bullish_confirm: held_action,unheld_action,level="持有；买入日低点作防守","可考虑试仓1/3","确认买点"
    elif not is_etf and weekly_safe and n["kind"]=="up" and "回踩" in n["phase"] and low_j and n_contracted: held_action,unheld_action,level="持有观察，未确认前不加仓","观察买入；等止跌K线/N+1","观察买入"
    elif is_etf and weekly_safe and last["close"]<daily["bbi"] and daily["j"]<13: held_action,unheld_action,level="持有观察，跌破MA60则降仓","观察日线重新上穿BBI","观察买入"
    elif weekly_safe and last["close"]>=daily["bbi"]: held_action,unheld_action,level="持有，不追涨加仓","等待缩量回踩或新确认点","持有"
    else: held_action,unheld_action,level="控制仓位，等待条件共振","继续等待，不提前猜底","等待"
    status="偏强" if weekly_safe and daily["aboveBbi"] else "偏弱" if not weekly["aboveBbi"] and not daily["aboveBbi"] else "震荡/待确认"
    supports=[x for x in (mas["21"],mas["34"],mas["60"],daily["bbi"],n.get("l2")) if x and x<last["close"]]; pressures=[x for x in (mas["21"],mas["34"],mas["60"],daily["bbi"],hi20,n.get("h1")) if x and x>last["close"]]; support=max(supports,default=low20); pressure=min(pressures,default=hi20)
    next_watch=[f"收盘能否守住 {support:.3f} 附近",f"能否带量突破 {pressure:.3f} 附近"]
    if level=="观察买入": next_watch.append("等待止跌下影线，或放量中阳线完成N+1；未确认不先买")
    elif level in ("红线","减仓"): next_watch.append("优先看能否快速收回BBI/MA60；不能收回则按红线继续降风险")
    elif level=="止盈": next_watch.append("减仓后观察缩量回踩，不因继续上涨追回")
    if is_etf: next_watch.append("ETF以周/日BBI为主，N形只作辅助，不强套个股形态")
    checks=[{"name":"月线环境","ok":month_safe,"text":"月线站上BBI且BBI不向下"},{"name":"周线安全区","ok":weekly_safe,"text":"周线站上BBI且BBI不向下"},{"name":"日线N回踩","ok":n["kind"]=="up" and "回踩" in n["phase"],"text":n["phase"]},{"name":"KDJ低位","ok":low_j,"text":f"J={daily['j']}（标准<13，负值更佳）"},{"name":"回踩缩量","ok":n_contracted,"text":f"N低点量/前高量={n.get('volumeRatio','—')}（参考≤0.65）"},{"name":"止跌/N+1","ok":stop_candle or bullish_confirm,"text":"已有形态确认" if stop_candle or bullish_confirm else "尚无明确确认K线"}]
    series=[{"d":rows[i]["date"],"c":rows[i]["close"],"b":fmt(daily_bbis[i],3)} for i in range(max(0,len(rows)-90),len(rows))]
    return {**item,"date":last["date"],"close":last["close"],"pct":last["pct"],"ret20":fmt(change_pct(last["close"],closes[-21])),"ret60":fmt(change_pct(last["close"],closes[-61])),"ma":{k:fmt(x,3) for k,x in mas.items()},"bbi":daily["bbi"],"kdjJ":daily["j"],"bias55":fmt(change_pct(last["close"],mas["55"]),1),"volRatio":fmt(vol_ratio,2),"pos20":fmt(pos20,1),"hi20":fmt(hi20,3),"low20":fmt(low20,3),"status":status,"actionLevel":level,"heldAction":held_action,"unheldAction":unheld_action,"action":held_action,"reasons":reasons,"risks":risks or ["当前未触发材料中的突出卖出红线"],"nextWatch":next_watch,"checks":checks,"timeframes":{"month":monthly,"week":weekly,"day":daily},"n":n,"signals":{"crossUpBbi":cross_up_bbi,"crossDownBbi":cross_down_bbi,"crossDownMa60":cross_down_ma60,"stopCandle":stop_candle,"bullishConfirm":bullish_confirm,"highVolumeStall":high_volume_stall,"topBear":top_bear},"series":series}

def main():
    data=[]; errors=[]; old={}; path=ROOT/"data.js"
    if path.exists():
        try:
            raw=path.read_text(encoding="utf-8"); payload=json.loads(raw[len("window.REVIEW_DATA="):].rstrip(";")); old={x["code"]:x for x in payload.get("items",[])}
        except Exception: pass
    for watched in WATCH:
        try: data.append(analyze(get(*watched)))
        except Exception as exc:
            errors.append({"code":watched[1],"error":str(exc)})
            if watched[1] in old: data.append({**old[watched[1]],"stale":True})
        time.sleep(.35+random.random()*.25)
    if not data: raise SystemExit("全部行情获取失败，保留原有 data.js。")
    latest=max(x["date"] for x in data)
    payload={"generatedAt":datetime.now().astimezone().isoformat(timespec="seconds"),"marketDate":latest,"source":"东方财富为主；新浪财经为备用（公开复权日线）","items":data,"errors":errors,"method":"按材料规则做多周期筛查：月线看环境、周线看安全区、日线找N形/BBI买卖点；结合KDJ-J连续状态、量价、MA60和止跌/N+1确认。ETF以BBI为主。操作栏同时给出未持有与已持有方案，仅作学习复盘。"}
    path.write_text("window.REVIEW_DATA="+json.dumps(payload,ensure_ascii=False,separators=(",",":"))+";",encoding="utf-8"); print(f"已更新 {len(data)} 个品种，行情日期 {latest}")
if __name__=="__main__": main()

