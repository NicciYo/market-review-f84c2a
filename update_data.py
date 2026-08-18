import json, math, statistics, urllib.parse, urllib.request, time, random, subprocess, tempfile, re, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
SINA = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData"
CURL = shutil.which("curl.exe") or shutil.which("curl")
WATCH = [
    ("芯片ETF易方达","516350","1","芯片ETF"),("科创新材料ETF博时","588010","1","科创ETF"),
    ("科创100ETF华夏","588800","1","科创ETF"),("科创机械ETF嘉实","588850","1","机械ETF"),
    ("农业银行","601288","1","银行"),("邮储银行","601658","1","银行"),
    ("快克智能","603203","1","个股"),("格力电器","000651","0","个股"),("福晶科技","002222","0","个股"),
    ("中天精装","002989","0","个股"),("机器人ETF易方达","159530","0","机器人ETF"),
    ("长芯博创","300548","0","个股"),("罗博特科","300757","0","个股")]

def get(name, code, market, group, limit=180):
    params={"secid":f"{market}.{code}","klt":"101","fqt":"1","lmt":str(limit),"end":"20500101",
            "fields1":"f1,f2,f3,f4,f5,f6","fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}
    url=API+"?"+urllib.parse.urlencode(params)
    last_error=None; obj=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://quote.eastmoney.com/"})
            with urllib.request.urlopen(req,timeout=25) as resp: obj=json.loads(resp.read().decode("utf-8"))
            if obj.get("data") and obj["data"].get("klines"): break
            raise RuntimeError("接口返回空行情")
        except Exception as e:
            last_error=e
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
        if not CURL: raise RuntimeError("系统中未找到 curl，且主数据源读取失败")
        curl=subprocess.run([CURL,"-sS","-L","--retry","2","--connect-timeout","8","--max-time","20","-A","Mozilla/5.0","-e","https://finance.sina.com.cn/",su],capture_output=True,text=True,encoding="utf-8",timeout=60)
        m=re.search(r"\(\s*(\[.*\])\s*\);",curl.stdout,re.S)
        if not m: raise RuntimeError(curl.stderr.strip() or str(last_error))
        sr=json.loads(m.group(1)); rows=[]
        prev=None
        for x in sr:
            close=float(x["close"]); change=(close/prev-1)*100 if prev else 0
            rows.append({"date":x["day"][:10],"open":float(x["open"]),"close":close,"high":float(x["high"]),"low":float(x["low"]),"volume":float(x["volume"]),"pct":change})
            prev=close
        return {"name":name,"code":code,"group":group,"dataSource":"新浪财经日线（备用）","rows":rows}
    rows=[]
    for line in obj["data"]["klines"]:
        x=line.split(",")
        rows.append({"date":x[0],"open":float(x[1]),"close":float(x[2]),"high":float(x[3]),"low":float(x[4]),"volume":float(x[5]),"pct":float(x[8])})
    return {"name":name,"code":code,"group":group,"dataSource":"东方财富日线（主）","rows":rows}

def sma(vals,n): return sum(vals[-n:])/n if len(vals)>=n else None
def ema(vals,n):
    a=2/(n+1); out=[]
    for v in vals: out.append(v if not out else a*v+(1-a)*out[-1])
    return out
def pct(a,b): return (a/b-1)*100 if b else 0
def f(v,d=2): return None if v is None else round(v,d)

def analyze(item):
    r=item.pop("rows"); c=[x["close"] for x in r]; h=[x["high"] for x in r]; lo=[x["low"] for x in r]; v=[x["volume"] for x in r]
    last=r[-1]; prev=r[-2]; mas={str(n):sma(c,n) for n in (5,8,13,21,34,55,60)}
    bbi=statistics.mean([sma(c,n) for n in (3,6,12,24)])
    e12,e26=ema(c,12),ema(c,26); dif=[a-b for a,b in zip(e12,e26)]; dea=ema(dif,9); hist=[2*(a-b) for a,b in zip(dif,dea)]
    k=d=50.0; js=[]
    for i,x in enumerate(r):
        start=max(0,i-8); hh=max(h[start:i+1]); ll=min(lo[start:i+1]); rv=(x["close"]-ll)/(hh-ll)*100 if hh!=ll else 50
        k=2*k/3+rv/3; d=2*d/3+k/3; js.append(3*k-2*d)
    vol5=sma(v,5); vol10=sma(v,10); vol_ratio=last["volume"]/vol10 if vol10 else 1
    hi20=max(h[-20:]); low20=min(lo[-20:]); pos20=(last["close"]-low20)/(hi20-low20)*100 if hi20!=low20 else 50
    ret20=pct(last["close"],c[-21]) if len(c)>21 else 0; ret60=pct(last["close"],c[-61]) if len(c)>61 else 0
    bias55=pct(last["close"],mas["55"]) if mas["55"] else None
    score=0; reasons=[]; risks=[]
    if last["close"]>mas["60"]: score+=2; reasons.append("收盘站在 MA60 上方")
    else: score-=2; risks.append("收盘位于 MA60 下方")
    if last["close"]>bbi: score+=1; reasons.append("收盘站在 BBI 上方")
    else: score-=1; risks.append("收盘位于 BBI 下方")
    if mas["21"]>mas["34"]>mas["60"]: score+=2; reasons.append("中长期均线呈多头顺序")
    elif mas["21"]<mas["34"]<mas["60"]: score-=2; risks.append("中长期均线呈空头顺序")
    if hist[-1]>0 and hist[-1]>=hist[-2]: score+=1; reasons.append("MACD 红柱增强")
    elif hist[-1]<0 and hist[-1]<=hist[-2]: score-=1; risks.append("MACD 绿柱扩大")
    if vol_ratio>1.25 and last["pct"]>0: score+=1; reasons.append("上涨伴随明显增量")
    if vol_ratio>1.25 and last["pct"]<0: score-=1; risks.append("下跌伴随明显放量")
    if js[-1]>100: risks.append("KDJ-J 进入极热区")
    if js[-1]<13: reasons.append("KDJ-J 处于低位区")
    if pos20>88: risks.append("价格接近 20 日区间高位")
    if pos20<12: reasons.append("价格接近 20 日区间低位")
    status="偏强" if score>=3 else "偏弱" if score<=-3 else "震荡/待确认"
    action="持有观察，不追高" if score>=3 else "控制仓位，等站回 BBI/MA60" if score<=-3 else "等待放量突破或回踩确认"
    if js[-1]>100 or (bias55 is not None and bias55>18): action="已有仓位可分批保护利润；不追涨"
    support=max([x for x in [mas["21"],mas["34"],bbi] if x<last["close"]], default=low20)
    pressure=min([x for x in [mas["21"],mas["34"],bbi,hi20] if x>last["close"]], default=hi20)
    next_watch=[f"能否守住 {support:.3f} 附近支撑",f"能否有效突破 {pressure:.3f} 附近压力"]
    if vol_ratio<.7: next_watch.append("量能偏低，突破需补量确认")
    elif vol_ratio>1.3: next_watch.append("量能显著放大，观察次日是否有承接")
    return {**item,"date":last["date"],"close":last["close"],"pct":last["pct"],"ret20":f(ret20),"ret60":f(ret60),
      "ma":{k:f(x,3) for k,x in mas.items()},"bbi":f(bbi,3),"macd":{"dif":f(dif[-1],4),"dea":f(dea[-1],4),"hist":f(hist[-1],4),"histPrev":f(hist[-2],4)},
      "kdjJ":f(js[-1],1),"bias55":f(bias55,1),"volRatio":f(vol_ratio,2),"pos20":f(pos20,1),"hi20":f(hi20,3),"low20":f(low20,3),
      "score":score,"status":status,"reasons":reasons or ["暂未出现明确正向共振"],"risks":risks or ["暂无突出技术红线"],
      "action":action,"nextWatch":next_watch,"series":[{"d":x["date"],"c":x["close"]} for x in r[-60:]]}

def main():
    data=[]; errors=[]; old={}
    path=ROOT/"data.js"
    if path.exists():
        try:
            raw=path.read_text(encoding="utf-8"); payload=json.loads(raw[len("window.REVIEW_DATA="):].rstrip(";")); old={x["code"]:x for x in payload.get("items",[])}
        except Exception: pass
    for w in WATCH:
        try: data.append(analyze(get(*w)))
        except Exception as e:
            errors.append({"code":w[1],"error":str(e)})
            if w[1] in old: data.append({**old[w[1]],"stale":True})
        time.sleep(.35+random.random()*.25)
    if not data: raise SystemExit("全部行情获取失败，保留原有 data.js。")
    latest=max(x["date"] for x in data)
    payload={"generatedAt":datetime.now().astimezone().isoformat(timespec="seconds"),"marketDate":latest,"source":"东方财富为主；新浪财经为备用（均为公开日线）","items":data,"errors":errors,
      "method":"周/日趋势框架的日线执行版：MA21/34/60、BBI、MACD、KDJ-J、BIAS55、量比与20日位置。结论为规则化观察，不构成买卖指令。"}
    path.write_text("window.REVIEW_DATA="+json.dumps(payload,ensure_ascii=False,separators=(",",":"))+";",encoding="utf-8")
    print(f"已更新 {len(data)} 个品种，行情日期 {latest}")

if __name__=="__main__": main()

