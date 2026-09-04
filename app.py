import streamlit as st
import sqlite3, requests, re, io
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from datetime import datetime
import pandas as pd

st.set_page_config(page_title='HUNTER TECHS',page_icon='🔎',layout='wide')
DB='hunter.db'; HEAD={'User-Agent':'Mozilla/5.0'}
QUERIES=['"novo CIO" empresa Brasil','"novo CTO" empresa Brasil','"novo gerente de TI" empresa','"transformação digital" empresa','"migração para cloud" empresa','"RFP" "segurança da informação"','"solicitação de proposta" TI empresa','"contratação" "serviços gerenciados" TI','"fornecedor" cybersecurity empresa','"cotação" "segurança da informação"']
TRIG=['novo cio','novo cto','novo diretor','novo gerente de ti','expansão','aquisição','nova unidade','nova filial','crescimento','transformação digital','migração','cloud','implantação de erp','incidente de segurança','reestruturação de ti']
NEED=['rmm','edr','backup','segurança','monitoramento','endpoint','firewall','sase','serviços gerenciados','infraestrutura','cloud','nuvem','cybersecurity','continuidade','governança']
INTENT=['rfp','rfq','solicitação de proposta','cotação','busca por fornecedor','processo de contratação','contratação de serviço','troca de fornecedor','busca de parceiro','request for proposal','request for quotation']
DM=['diretor de ti','diretor de tecnologia','cio','cto','gerente de ti']

def con():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.executescript('''CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, name TEXT UNIQUE, url TEXT, created TEXT, updated TEXT);CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, company_id INTEGER,title TEXT,url TEXT,collected TEXT,content TEXT,UNIQUE(company_id,url));CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY,company_id INTEGER,source_id INTEGER,kind TEXT,evidence TEXT,UNIQUE(company_id,source_id,kind,evidence));CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY,company_id INTEGER UNIQUE,trigger TEXT,need TEXT,pain TEXT,intent TEXT,dm TEXT,timing TEXT,score INTEGER,confidence TEXT,class TEXT,next_action TEXT,reason TEXT,updated TEXT);CREATE TABLE IF NOT EXISTS hunts(id INTEGER PRIMARY KEY,started TEXT,finished TEXT,status TEXT,companies INTEGER,new INTEGER,updated INTEGER,discarded INTEGER);'''); return c

def search(q):
 try:
  r=requests.get('https://html.duckduckgo.com/html/?q='+quote_plus(q),headers=HEAD,timeout=15); s=BeautifulSoup(r.text,'html.parser')
  return [(a.get_text(' ',strip=True),a.get('href')) for a in s.select('.result__a')[:6] if a.get('href')]
 except: return []

def fetch(u):
 try:
  r=requests.get(u,headers=HEAD,timeout=15); r.raise_for_status(); s=BeautifulSoup(r.text,'html.parser')
  for x in s(['script','style','noscript']): x.decompose()
  return (s.title.get_text(' ',strip=True) if s.title else u,re.sub(r'\s+',' ',s.get_text(' ',strip=True))[:80000],r.url)
 except: return None,None,u

def hits(t,terms): return [x for x in terms if x in (t or '').lower()]
def company(title):
 x=re.split(r'\s[-|–—:]\s',title or '')[0].strip()
 return x if 1<len(x.split())<=8 and len(x)<=100 else None

def hunt():
 c=con(); cur=c.cursor(); cur.execute('INSERT INTO hunts(started,status) VALUES(?,?)',(datetime.now().isoformat(),'RUNNING')); hid=cur.lastrowid;c.commit(); urls=set(); comps=set();new=upd=discard=0
 try:
  for q in QUERIES:
   for title,url in search(q):
    if url in urls: continue
    urls.add(url); title,text,url=fetch(url)
    if not text: discard+=1;continue
    name=company(title)
    if not name: discard+=1;continue
    comps.add(name); row=cur.execute('SELECT id FROM companies WHERE lower(name)=lower(?)',(name,)).fetchone()
    if row: cid=row['id'];cur.execute('UPDATE companies SET url=?,updated=? WHERE id=?',(url,datetime.now().isoformat(),cid))
    else: cur.execute('INSERT INTO companies(name,url,created,updated) VALUES(?,?,?,?)',(name,url,datetime.now().isoformat(),datetime.now().isoformat()));cid=cur.lastrowid
    cur.execute('INSERT OR IGNORE INTO sources(company_id,title,url,collected,content) VALUES(?,?,?,?,?)',(cid,title,url,datetime.now().isoformat(),text[:30000]));sid=cur.execute('SELECT id FROM sources WHERE company_id=? AND url=?',(cid,url)).fetchone()['id']
    tr=hits(text,TRIG); nd=hits(text,NEED); it=hits(text,INTENT); dm=hits(text,DM)
    sentences=re.split(r'(?<=[.!?])\s+',text); ev=[s.strip() for s in sentences if 35<=len(s)<=700 and any(k in s.lower() for k in TRIG+NEED+INTENT+DM)][:8]
    for e in ev:
     kind='BUYING_INTENT' if any(k in e.lower() for k in INTENT) else ('BUSINESS_TRIGGER' if any(k in e.lower() for k in TRIG) else 'NEED_SIGNAL')
     cur.execute('INSERT OR IGNORE INTO signals(company_id,source_id,kind,evidence) VALUES(?,?,?,?)',(cid,sid,kind,e))
    intent='HIGH' if it else 'NONE'; need='HIGH' if nd else 'NONE'; pain='MEDIUM' if tr and nd else 'NONE'; timing='HIGH' if tr else 'NONE'; dmval='LIKELY' if dm else 'NONE'; icp=7
    raw=icp+(25 if intent=='HIGH' else 0)+(20 if need=='HIGH' else 0)+(12 if pain=='MEDIUM' else 0)+(10 if timing=='HIGH' else 0)+(7 if dmval=='LIKELY' else 0);score=min(raw,{'NONE':30,'LOW':55,'MEDIUM':75,'HIGH':90,'VERY HIGH':100}[intent])
    conf='HIGH' if it and nd else ('MEDIUM' if it or nd else 'LOW')
    cls='IGNORE' if not ev else ('HOT' if score>=75 and intent in ('HIGH','VERY HIGH') and conf in ('HIGH','MEDIUM') else ('WARM' if score>=55 and intent in ('MEDIUM','HIGH','VERY HIGH') else ('WATCH' if score>=30 else 'IGNORE')))
    action={'HOT':'Abordar decisor e validar dor.','WARM':'Abordagem consultiva para confirmar necessidade.','WATCH':'Monitorar novos sinais.','IGNORE':'Não abordar; evidência insuficiente.'}[cls]
    old=cur.execute('SELECT id FROM opportunities WHERE company_id=?',(cid,)).fetchone()
    cur.execute('''INSERT INTO opportunities(company_id,trigger,need,pain,intent,dm,timing,score,confidence,class,next_action,reason,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET trigger=excluded.trigger,need=excluded.need,pain=excluded.pain,intent=excluded.intent,dm=excluded.dm,timing=excluded.timing,score=excluded.score,confidence=excluded.confidence,class=excluded.class,next_action=excluded.next_action,reason=excluded.reason,updated=excluded.updated''',(cid,tr[0] if tr else 'UNKNOWN',need,pain,intent,dmval,timing,score,conf,cls,action,f'ICP 7/15; Intent; Need; Pain; Timing; DM. Raw={raw}; Cap aplicado={score}.',datetime.now().isoformat()))
    if cls=='IGNORE': discard+=1
    elif old: upd+=1
    else: new+=1
    c.commit()
  cur.execute('UPDATE hunts SET finished=?,status=?,companies=?,new=?,updated=?,discarded=? WHERE id=?',(datetime.now().isoformat(),'COMPLETED',len(comps),new,upd,discard,hid));c.commit();return hid,len(comps),new,upd,discard
 finally:c.close()

def rows():
 c=con(); r=c.execute('SELECT o.*,c.name,c.url FROM opportunities o JOIN companies c ON c.id=o.company_id ORDER BY o.score DESC,o.updated DESC').fetchall();c.close();return r

def evs(oid):
 c=con();r=c.execute('SELECT s.kind,s.evidence,src.title,src.url,src.collected FROM signals s JOIN sources src ON src.id=s.source_id JOIN opportunities o ON o.company_id=s.company_id WHERE o.id=? ORDER BY src.collected DESC',(oid,)).fetchall();c.close();return r

st.title('🔎 HUNTER TECHS');st.caption('Opportunity Intelligence Radar — CAÇA REAL')
c=con();stats=[c.execute('SELECT COUNT(*) n FROM companies').fetchone()['n'],c.execute("SELECT COUNT(*) n FROM opportunities WHERE class!='IGNORE'").fetchone()['n'],c.execute("SELECT COUNT(*) n FROM opportunities WHERE class='HOT'").fetchone()['n'],c.execute("SELECT COUNT(*) n FROM opportunities WHERE class='WARM'").fetchone()['n']];c.close()
a,b,d,e=st.columns(4);a.metric('Empresas',stats[0]);b.metric('Oportunidades',stats[1]);d.metric('HOT',stats[2]);e.metric('WARM',stats[3])
if st.button('🔎 IR PARA CAÇA',type='primary',use_container_width=True):
 with st.spinner('Executando caça real na web...'):
  try:
   x=hunt();st.success(f'Caça #{x[0]} concluída — {x[1]} empresas | {x[2]} novas | {x[3]} atualizadas | {x[4]} descartadas.')
  except Exception as ex: st.error(str(ex))
st.divider();f=st.selectbox('Classificação',['TODAS','HOT','WARM','WATCH','IGNORE'])
rr=[r for r in rows() if f=='TODAS' or r['class']==f]
for o in rr:
 with st.container(border=True):
  x,y,z=st.columns([5,1,1]);x.subheader({'HOT':'🔥','WARM':'🟠','WATCH':'👁️','IGNORE':'⛔'}[o['class']]+' '+o['name']);x.caption(o['url']);y.metric('Score',o['score']);z.metric('Confidence',o['confidence']);st.write(f"**Intent:** {o['intent']} | **Need:** {o['need']} | **Timing:** {o['timing']} | **DM:** {o['dm']}");st.write('**Trigger:**',o['trigger']);st.write('**Pain/Risk:**',o['pain']);st.write('**Próxima ação:**',o['next_action'])
  with st.expander('Evidências'): st.write(o['reason']);[st.markdown(f"- **{v['kind']} / FACT:** {v['evidence']}  \nFonte: {v['title']} — {v['url']}") for v in evs(o['id'])]
