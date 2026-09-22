#!/usr/bin/env python3
"""Market Radar V2.2 official Taiwan-market enrichment.

Adds independently sourced TWSE institutional totals to live.json and writes
sector-v22.json from TWSE industry-index / institutional-industry endpoints.
Fail closed: if an official response cannot be verified, the field is omitted.
"""
from __future__ import annotations
import json, re, ssl
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; TZ=ZoneInfo('Asia/Taipei')
UA='TW-Market-Radar/2.2 (+official-source-enrichment)'

def get_json(url):
    req=Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    with urlopen(req,timeout=30,context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode('utf-8','replace'))

def n(v):
    if v is None:return None
    s=str(v).replace(',','').replace('−','-').strip()
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    return float(m.group()) if m else None

def twse_web(path,date):
    q=urlencode({'response':'json','date':date.replace('-',''),'selectType':'ALL'})
    return get_json('https://www.twse.com.tw/rwd/zh/'+path+'?'+q)

def rows(obj):
    if isinstance(obj,dict) and obj.get('fields') and obj.get('data'):
        return [dict(zip(obj['fields'],r)) for r in obj['data']]
    return []

def money_to_yi(v):
    x=n(v); return None if x is None else x/100_000_000

def fmt_yi(x): return f'{x:+,.2f} 億' if x is not None else 'N/A'

def find_col(d, needles):
    for k in d:
        if all(z in k for z in needles): return k
    return None

def institutional(date):
    obj=twse_web('fund/BFI82U',date); rr=rows(obj)
    if obj.get('stat')!='OK' or not rr: raise ValueError('TWSE BFI82U unavailable')
    out={}
    dealer=0.0; dealer_seen=False
    for r in rr:
        typ=str(next(iter(r.values()),''))
        netk=find_col(r,['買賣','差額']) or find_col(r,['買賣超'])
        val=money_to_yi(r.get(netk)) if netk else None
        if val is None: continue
        if '外資' in typ and '自營' not in typ: out['foreignSpotOfficial']=val
        elif '投信' in typ: out['investmentTrust']=val
        elif '自營商' in typ:
            dealer+=val; dealer_seen=True
    if dealer_seen: out['dealer']=dealer
    return out

def industry_flow(path,date):
    try: obj=twse_web('fund/'+path,date); rr=rows(obj)
    except Exception:return {}
    ans={}
    for r in rr:
        namek=find_col(r,['產業']) or find_col(r,['類股']) or find_col(r,['名稱'])
        netk=find_col(r,['買賣','差額']) or find_col(r,['買賣超'])
        if namek and netk:
            val=money_to_yi(r.get(netk))
            if val is not None: ans[str(r.get(namek)).strip()]=val
    return ans

def industry_price(date):
    try: obj=twse_web('afterTrading/MI_INDEX',date)
    except Exception:return {}
    ans={}
    for t in obj.get('tables') or []:
        fs=t.get('fields') or []
        if not fs: continue
        if not any('指數' in str(x) or '類股' in str(x) for x in fs): continue
        for row in t.get('data') or []:
            d=dict(zip(fs,row)); name=str(row[0]).strip() if row else ''
            if not name: continue
            ck=next((k for k in d if '漲跌百分比' in k or '漲跌幅' in k),None)
            if ck:
                val=n(d.get(ck));
                if val is not None: ans[name]=val
    return ans

def best_match(mapping,label):
    aliases={'半導體':['半導體'],'電子零組件':['電子零組件'],'金融':['金融保險','金融'],'航運':['航運'],'資訊服務':['資訊服務'],'上櫃電子':['電子']}
    for a in aliases.get(label,[label]):
        for k,v in mapping.items():
            if a in k:return v
    return None

def main():
    p=DATA/'live.json'; live=json.loads(p.read_text(encoding='utf-8'))
    date=str(((live.get('metrics') or {}).get('taiex') or {}).get('asOf') or '')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date): raise SystemExit('No verified TAIEX asOf; enrichment skipped')
    errors=[]
    try:
        inst=institutional(date)
        m=live.setdefault('metrics',{})
        for key,label in [('investmentTrust','投信'),('dealer','自營商')]:
            if key in inst:
                m[key]={'value':fmt_yi(inst[key]),'display':fmt_yi(inst[key]),'rawValueYi':round(inst[key],4),'asOf':date,'source':'TWSE BFI82U','state':'official'}
        if 'foreignSpotOfficial' in inst:
            m['foreignSpotOfficial']={'value':fmt_yi(inst['foreignSpotOfficial']),'rawValueYi':round(inst['foreignSpotOfficial'],4),'asOf':date,'source':'TWSE BFI82U','state':'official'}
    except Exception as e: errors.append('institutional: '+str(e))
    price=industry_price(date); foreign=industry_flow('TWT38U',date); trust=industry_flow('TWT43U',date); dealer=industry_flow('TWT44U',date)
    names=['半導體','電子零組件','金融','航運','資訊服務','上櫃電子']
    sec=[]
    for name in names:
        pv=best_match(price,name); fv=best_match(foreign,name); tv=best_match(trust,name); dv=best_match(dealer,name)
        sec.append({'name':name,'priceChangePct':pv,'foreignYi':fv,'trustYi':tv,'dealerYi':dv,'asOf':date,'source':'TWSE' if any(v is not None for v in (pv,fv,tv,dv)) else 'N/A'})
    (DATA/'sector-v22.json').write_text(json.dumps({'generatedAt':datetime.now(TZ).isoformat(timespec='seconds'),'asOf':date,'sectors':sec,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    live.setdefault('v22',{})['enrichedAt']=datetime.now(TZ).isoformat(timespec='seconds'); live['v22']['errors']=errors
    p.write_text(json.dumps(live,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V2.2 enrichment complete',date,'errors=',errors)
if __name__=='__main__': main()
