import streamlit as st
import sqlite3, requests, pandas as pd, io, re, hashlib
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlparse

st.set_page_config(page_title="HUNTER TECHS", page_icon="🔎", layout="wide")

DB = "hunter.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126 Safari/537.36 TECHS-Hunter/5.0"
}

# The Hunter searches for observable commercial/operational signals.
# It does NOT treat a generic technology mention as buying intent.
QUERIES = [
    '"RFP" OR "RFQ" "segurança da informação" Brasil',
    '"solicitação de proposta" "serviços de TI" Brasil',
    '"contratação" "serviços gerenciados" TI Brasil',
    '"contratação" "segurança cibernética" Brasil',
    '"busca de fornecedor" TI segurança Brasil',
    '"novo CIO" empresa Brasil',
    '"novo CTO" empresa Brasil',
    '"novo diretor de tecnologia" empresa Brasil',
    '"novo gerente de TI" empresa Brasil',
    '"migração para cloud" empresa Brasil',
    '"migração para nuvem" empresa Brasil',
    '"modernização da infraestrutura" empresa Brasil',
    '"transformação digital" infraestrutura empresa Brasil',
    '"incidente de segurança" empresa Brasil',
    'ransomware empresa brasileira 2026',
    '"expansão" "novas lojas" empresa Brasil',
    '"nova unidade" empresa "tecnologia" Brasil',
    '"abertura" "novas unidades" empresa Brasil tecnologia',
    '"vaga" "segurança da informação" empresa Brasil',
    '"vaga" "infraestrutura de TI" empresa Brasil',
    '"vaga" "SOC" empresa Brasil',
    '"vaga" "analista de infraestrutura" empresa Brasil',
]

INTENT_TERMS = [
    "rfp", "rfq", "request for proposal", "request for quotation",
    "solicitação de proposta", "solicitação de cotação", "solicitação de orçamento",
    "cotação", "orçamento", "processo de contratação", "processo de compras",
    "contratação de fornecedor", "busca de fornecedor", "busca por fornecedor",
    "seleção de fornecedor", "convidou fornecedores", "fornecedores interessados",
    "licitação", "edital", "pregão", "concorrência", "tomada de preços",
    "troca de fornecedor", "busca de parceiro"
]

NEED_TERMS = [
    "rmm", "edr", "backup", "segurança da informação", "segurança cibernética",
    "cybersecurity", "monitoramento de infraestrutura", "monitoramento de ti",
    "gestão de endpoints", "endpoint", "firewall", "sase", "serviços gerenciados",
    "managed services", "infraestrutura de ti", "infraestrutura tecnológica",
    "cloud", "nuvem", "continuidade", "disaster recovery", "recuperação de desastre",
    "governança de ti", "observabilidade", "soc", "mssp"
]

TRIGGER_TERMS = [
    "novo cio", "novo cto", "novo diretor de ti", "novo diretor de tecnologia",
    "novo gerente de ti", "novo responsável por ti", "expansão", "nova unidade",
    "nova filial", "aquisição", "fusão", "crescimento", "transformação digital",
    "migração para cloud", "migração para nuvem", "implantação de erp",
    "incidente de segurança", "ataque cibernético", "reestruturação de ti",
    "modernização da infraestrutura"
]

PAIN_TERMS = [
    "indisponibilidade", "downtime", "parada", "falha", "incidente",
    "ataque", "vulnerabilidade", "risco", "interrupção", "perda de dados",
    "vazamento", "ransomware", "continuidade", "obsolescência", "falta de equipe",
    "sobrecarga", "24x7", "tempo de resposta"
]

DM_TERMS = [
    "cio", "cto", "diretor de ti", "diretor de tecnologia",
    "gerente de ti", "gerente de tecnologia", "head de tecnologia",
    "diretor de infraestrutura", "diretor de segurança"
]

GENERIC_COMPANIES = {
    "google news", "google", "youtube", "facebook", "linkedin", "reuters",
    "exame", "valor", "estadao", "estadião", "folha", "globo", "uol",
    "terra", "cnn", "forbes", "g1", "canaltech", "tecmundo", "olhar digital",
    "infomoney", "istoé", "isto é", "estadão", "news"
}

def now():
    return datetime.now().isoformat(timespec="seconds")

def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    required = {
        "companies": {"id","name","website","icp","created_at","updated_at"},
        "sources": {"id","company_id","title","url","source_type","publisher","collected_at","content"},
        "signals": {"id","company_id","source_id","kind","evidence","evidence_type","created_at"},
        "opportunities": {"id","company_id","trigger_text","need","pain","intent","dm",
                          "timing","score","confidence","classification","next_action",
                          "reason","created_at","updated_at"},
        "hunts": {"id","started_at","finished_at","status","sources_found","signals_found","companies","new_opps",
                  "updated_opps","discarded"},
    }

    rebuild = False
    for table, columns in required.items():
        exists = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists:
            actual = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
            if not columns.issubset(actual):
                rebuild = True

    if rebuild:
        c.executescript("""
        DROP TABLE IF EXISTS signals;
        DROP TABLE IF EXISTS sources;
        DROP TABLE IF EXISTS opportunities;
        DROP TABLE IF EXISTS companies;
        DROP TABLE IF EXISTS hunts;
        """)

    c.executescript("""
    CREATE TABLE IF NOT EXISTS companies(
      id INTEGER PRIMARY KEY, name TEXT UNIQUE, website TEXT,
      icp TEXT DEFAULT 'UNKNOWN', created_at TEXT, updated_at TEXT);

    CREATE TABLE IF NOT EXISTS sources(
      id INTEGER PRIMARY KEY, company_id INTEGER, title TEXT, url TEXT UNIQUE,
      source_type TEXT DEFAULT 'NOTICIA', publisher TEXT, collected_at TEXT, content TEXT);

    CREATE TABLE IF NOT EXISTS signals(
      id INTEGER PRIMARY KEY, company_id INTEGER, source_id INTEGER, kind TEXT,
      evidence TEXT, evidence_type TEXT, created_at TEXT,
      UNIQUE(company_id,source_id,kind,evidence));

    CREATE TABLE IF NOT EXISTS opportunities(
      id INTEGER PRIMARY KEY, company_id INTEGER UNIQUE, trigger_text TEXT,
      need TEXT, pain TEXT, intent TEXT, dm TEXT, timing TEXT, score INTEGER,
      confidence TEXT, classification TEXT, next_action TEXT, reason TEXT,
      created_at TEXT, updated_at TEXT);

    CREATE TABLE IF NOT EXISTS hunts(
      id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT,
      sources_found INTEGER DEFAULT 0, signals_found INTEGER DEFAULT 0,
      companies INTEGER, new_opps INTEGER, updated_opps INTEGER, discarded INTEGER);
    """)
    # V6 migration/cleanup: never allow a source/publisher to survive as a company.
    placeholders = ",".join("?" * len(GENERIC_COMPANIES))
    c.execute(
        f"DELETE FROM opportunities WHERE company_id IN "
        f"(SELECT id FROM companies WHERE lower(name) IN ({placeholders}))",
        tuple(sorted(GENERIC_COMPANIES))
    )
    c.execute(
        f"DELETE FROM signals WHERE company_id IN "
        f"(SELECT id FROM companies WHERE lower(name) IN ({placeholders}))",
        tuple(sorted(GENERIC_COMPANIES))
    )
    c.execute(
        f"DELETE FROM sources WHERE company_id IN "
        f"(SELECT id FROM companies WHERE lower(name) IN ({placeholders}))",
        tuple(sorted(GENERIC_COMPANIES))
    )
    c.execute(
        f"DELETE FROM companies WHERE lower(name) IN ({placeholders})",
        tuple(sorted(GENERIC_COMPANIES))
    )
    c.commit()
    return c

def clean_text(x):
    return re.sub(r"\s+", " ", x or "").strip()

def term_hits(text, terms):
    low = (text or "").lower()
    return [t for t in terms if t in low]

def rss_search(query):
    url = (
        "https://news.google.com/rss/search?q=" + quote_plus(query) +
        "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        items = []
        for item in soup.find_all("item"):
            title = clean_text(item.title.get_text(" ", strip=True) if item.title else "")
            link = item.link.get_text(strip=True) if item.link else ""
            desc = clean_text(item.description.get_text(" ", strip=True) if item.description else "")
            pub = clean_text(item.pubDate.get_text(" ", strip=True) if item.pubDate else "")
            source = clean_text(item.source.get_text(" ", strip=True) if item.source else "")
            if link:
                items.append({
                    "title": title, "url": link, "description": desc,
                    "published": pub, "publisher": source
                })
        return items[:15]
    except Exception:
        return []

def pncp_search(max_pages=3):
    """Consulta pública, sem chave, do PNCP; prioriza propostas abertas."""
    base="https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
    data_final=datetime.now().strftime("%Y%m%d")
    items=[]
    for page in range(1,max_pages+1):
        try:
            r=requests.get(base,params={"dataFinal":data_final,"pagina":page,"tamanhoPagina":50},headers=HEADERS,timeout=25)
            r.raise_for_status(); payload=r.json()
            rows=payload.get("data",payload if isinstance(payload,list) else [])
            if not rows: break
            for row in rows:
                obj=clean_text(row.get("objetoCompra") or row.get("objeto") or "")
                if not obj or not (term_hits(obj,NEED_TERMS) or term_hits(obj,INTENT_TERMS) or term_hits(obj,TRIGGER_TERMS)): continue
                org=clean_text(row.get("nomeUnidade") or row.get("nomeOrgao") or row.get("orgaoEntidade") or "")
                ctrl=clean_text(row.get("numeroControlePNCP") or "")
                url=clean_text(row.get("linkSistemaOrigem") or "")
                if not url and ctrl: url="https://pncp.gov.br/app/editais/"+ctrl
                if not url: url="https://pncp.gov.br/"
                items.append({"title":clean_text((org+" — "+obj)[:500]),"url":url,"description":obj,
                              "published":clean_text(row.get("dataPublicacaoPncp") or ""),"publisher":org or "PNCP",
                              "source_type":"PNCP","company_candidate":org})
        except Exception: break
    return items

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for x in soup(["script","style","noscript","svg"]):
            x.decompose()
        title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
        text = clean_text(soup.get_text(" ", strip=True))
        return title, text[:120000], r.url
    except Exception:
        return None, None, url

def strip_publisher(title, publisher):
    t = clean_text(title)
    if publisher:
        # Google News commonly returns "headline - publisher".
        t = re.sub(r"\s+[-|–—]\s+" + re.escape(publisher) + r"\s*$", "", t, flags=re.I)
    return t

def valid_company(name):
    if not name:
        return False
    n = clean_text(name).strip(" -–—:,.")
    low = n.lower()
    if low in GENERIC_COMPANIES:
        return False
    if any(low == g or low.startswith(g + " ") for g in GENERIC_COMPANIES):
        return False
    if len(n) < 3 or len(n) > 100:
        return False
    words = n.split()
    if not (1 <= len(words) <= 9):
        return False
    if re.fullmatch(r"[0-9 .,%/-]+", n):
        return False
    return True

def extract_company(title, body, publisher, explicit_candidate=None):
    if explicit_candidate and valid_company(explicit_candidate) and explicit_candidate.lower() != (publisher or "").lower():
        return clean_text(explicit_candidate)
    t=strip_publisher(title,publisher); text=clean_text(t+" "+(body or "")[:35000]); candidates=[]
    def add(c):
        c=clean_text(c).strip(" -–—:,.()[]\"'"); c=re.sub(r"^(?:a|o|as|os)\s+","",c,flags=re.I)
        if valid_company(c) and c.lower() != (publisher or "").lower() and c.lower() not in [x.lower() for x in candidates]: candidates.append(c)
    patterns=[
      r"\b(?:empresa|grupo|companhia|holding|marca|rede)\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*){0,7})",
      r"^([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*){0,7}?)\s+(?:anuncia|anunciou|contrata|contratou|busca|buscou|expande|expandiu|abre|abriu|projeta|prevê|preve|investe|investiu)\b",
      r"^([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*){0,5})\s*[:\-–—]\s+"
    ]
    for ptn in patterns:
        for m in re.finditer(ptn,text,flags=re.I): add(m.group(1))
    return candidates[0] if candidates else None

def best_evidence(text, terms):
    sentences = re.split(r"(?<=[.!?])\s+", clean_text(text))
    scored = []
    for s in sentences:
        low = s.lower()
        if 45 <= len(s) <= 900:
            hits = sum(1 for term in terms if term in low)
            if hits:
                scored.append((hits, s))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [s for _, s in scored[:5]]

def classify(intent, need, pain, trigger, dm):
    # Buying intent is the hard gate. A technology mention alone cannot create HOT/WARM.
    intent_level = "VERY HIGH" if intent >= 3 else ("HIGH" if intent == 2 else ("MEDIUM" if intent == 1 else "NONE"))
    need_level = "HIGH" if need >= 2 else ("MEDIUM" if need == 1 else "NONE")
    pain_level = "HIGH" if pain >= 2 else ("MEDIUM" if pain == 1 else "NONE")
    timing_level = "HIGH" if trigger >= 2 else ("MEDIUM" if trigger == 1 else "NONE")
    dm_level = "LIKELY" if dm else "NONE"

    score = 7
    score += {"NONE":0,"MEDIUM":12,"HIGH":20,"VERY HIGH":25}[intent_level]
    score += {"NONE":0,"MEDIUM":11,"HIGH":20}[need_level]
    score += {"NONE":0,"MEDIUM":10,"HIGH":20}[pain_level]
    score += {"NONE":0,"MEDIUM":5,"HIGH":10}[timing_level]
    score += 7 if dm_level == "LIKELY" else 0

    cap = {"NONE":30,"MEDIUM":75,"HIGH":90,"VERY HIGH":100}.get(intent_level, 30)
    score = min(score, cap)

    # Strict classification.
    if intent_level == "VERY HIGH" and need_level != "NONE" and score >= 75:
        cls = "HOT"
    elif intent_level in ("HIGH","VERY HIGH") and need_level != "NONE" and score >= 55:
        cls = "WARM"
    elif need_level != "NONE" or intent_level != "NONE" or pain_level != "NONE":
        cls = "WATCH"
    else:
        cls = "IGNORE"

    confidence = "HIGH" if intent_level in ("HIGH","VERY HIGH") and need_level != "NONE" else (
        "MEDIUM" if intent_level != "NONE" or need_level != "NONE" or pain_level != "NONE" else "LOW"
    )
    return intent_level, need_level, pain_level, timing_level, dm_level, score, confidence, cls

def run_hunt():
    con=get_db(); cur=con.cursor(); cur.execute("INSERT INTO hunts(started_at,status) VALUES(?,?)",(now(),"RUNNING")); hunt_id=cur.lastrowid; con.commit()
    raw=[]; seen=set(); companies=set(); sources_found=signals_found=discarded=new_opps=updated=0
    try:
        # MILO: breadth first. Qualification happens only after collection.
        for q in QUERIES:
            for item in rss_search(q):
                if item["url"] not in seen: seen.add(item["url"]); raw.append(item)
        for item in pncp_search(max_pages=3):
            k=item["url"]+"|"+item["title"][:100]
            if k not in seen: seen.add(k); raw.append(item)
        sources_found=len(raw)
        for item in raw:
            desc=BeautifulSoup(item.get("description",""),"html.parser").get_text(" ",strip=True)
            page_title,page_text,final_url=fetch_page(item.get("url",""))
            title=page_title or strip_publisher(item.get("title",""),item.get("publisher","")); body=page_text or desc
            combined=clean_text(title+" "+desc+" "+body)
            for terms in (INTENT_TERMS,NEED_TERMS,TRIGGER_TERMS,PAIN_TERMS):
                if term_hits(combined,terms): signals_found+=1
            company=extract_company(title,body,item.get("publisher",""),item.get("company_candidate"))
            if not company:
                discarded+=1; continue
            companies.add(company)
            row=cur.execute("SELECT id FROM companies WHERE lower(name)=lower(?)",(company,)).fetchone()
            if row: cid=row["id"]; cur.execute("UPDATE companies SET website=?,updated_at=? WHERE id=?",(final_url,now(),cid))
            else: cur.execute("INSERT INTO companies(name,website,created_at,updated_at) VALUES(?,?,?,?)",(company,final_url,now(),now())); cid=cur.lastrowid
            cur.execute("INSERT OR IGNORE INTO sources(company_id,title,url,source_type,publisher,collected_at,content) VALUES(?,?,?,?,?,?,?)",(cid,title,final_url,item.get("source_type","NOTICIA"),item.get("publisher",""),now(),body[:40000]))
            sid=cur.execute("SELECT id FROM sources WHERE url=?",(final_url,)).fetchone()["id"]
            for kind,terms in (("BUYING_INTENT",INTENT_TERMS),("NEED_SIGNAL",NEED_TERMS),("BUSINESS_TRIGGER",TRIGGER_TERMS),("PAIN_RISK",PAIN_TERMS)):
                ev=best_evidence(combined,terms)
                if ev: cur.execute("INSERT OR IGNORE INTO signals(company_id,source_id,kind,evidence,evidence_type,created_at) VALUES(?,?,?,?,?,?)",(cid,sid,kind,ev[0],"FACT",now()))
            ih=term_hits(combined,INTENT_TERMS); nh=term_hits(combined,NEED_TERMS); th=term_hits(combined,TRIGGER_TERMS); ph=term_hits(combined,PAIN_TERMS); dh=term_hits(combined,DM_TERMS)
            # Trigger alone remains a signal; it cannot create an opportunity.
            if not (ih or nh or ph): discarded+=1; con.commit(); continue
            intent_level,need_level,pain_level,timing_level,dm_level,score,confidence,cls=classify(len(ih),len(nh),len(ph),len(th),bool(dh))
            if item.get("source_type")=="PNCP" and cls in ("HOT","WARM"): cls="WATCH"; confidence="HIGH"
            reason=(f"ICP FIT: UNKNOWN (7/15). Buying Intent: {intent_level}. Need Signal: {need_level}. Pain/Risk: {pain_level}. Timing: {timing_level}. Decision Maker: {dm_level}. Fonte: {item.get('publisher') or item.get('source_type','NOTICIA')} ({item.get('source_type','NOTICIA')}).")
            next_action={"HOT":"Abordar rapidamente o decisor e validar processo de compra, escopo e prazo.","WARM":"Abordagem consultiva baseada na evidência; confirmar necessidade, intenção e ICP.","WATCH":"Investigar/enriquecer o sinal antes da abordagem; buscar segunda evidência independente.","IGNORE":"Não abordar; evidência insuficiente."}[cls]
            old=cur.execute("SELECT id FROM opportunities WHERE company_id=?",(cid,)).fetchone()
            cur.execute("""INSERT INTO opportunities(company_id,trigger_text,need,pain,intent,dm,timing,score,confidence,classification,next_action,reason,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET trigger_text=excluded.trigger_text,need=excluded.need,pain=excluded.pain,intent=excluded.intent,dm=excluded.dm,timing=excluded.timing,score=excluded.score,confidence=excluded.confidence,classification=excluded.classification,next_action=excluded.next_action,reason=excluded.reason,updated_at=excluded.updated_at""",
              (cid,th[0] if th else "UNKNOWN",need_level,pain_level,intent_level,dm_level,timing_level,score,confidence,cls,next_action,reason,now(),now()))
            if cls=="IGNORE": discarded+=1
            elif old: updated+=1
            else: new_opps+=1
            con.commit()
        cur.execute("UPDATE hunts SET finished_at=?,status=?,sources_found=?,signals_found=?,companies=?,new_opps=?,updated_opps=?,discarded=? WHERE id=?",(now(),"COMPLETED",sources_found,signals_found,len(companies),new_opps,updated,discarded,hunt_id)); con.commit()
        return hunt_id,sources_found,signals_found,len(companies),new_opps,updated,discarded
    except Exception:
        cur.execute("UPDATE hunts SET finished_at=?,status=? WHERE id=?",(now(),"FAILED",hunt_id)); con.commit(); raise
    finally: con.close()

def opportunities():
    con = get_db()
    rows = con.execute(
        """SELECT o.*,c.name,c.website,c.icp FROM opportunities o
           JOIN companies c ON c.id=o.company_id
           ORDER BY o.score DESC,o.updated_at DESC"""
    ).fetchall()
    con.close()
    return rows

def evidence(oid):
    con = get_db()
    rows = con.execute(
        """SELECT s.kind,s.evidence,src.title,src.url,src.collected_at
           FROM signals s
           JOIN sources src ON src.id=s.source_id
           JOIN opportunities o ON o.company_id=s.company_id
           WHERE o.id=? ORDER BY src.collected_at DESC""", (oid,)
    ).fetchall()
    con.close()
    return rows

st.title("🔎 HUNTER TECHS")
st.caption("Opportunity Intelligence Radar — CAÇA REAL • V7 — MILO lê sinais | HUNTER peneira oportunidades")

con = get_db()
stats = [
    con.execute("SELECT COUNT(*) AS total FROM companies").fetchone()["total"],
    con.execute("SELECT COUNT(*) AS total FROM signals").fetchone()["total"],
    con.execute("SELECT COUNT(*) AS total FROM opportunities WHERE classification!='IGNORE'").fetchone()["total"],
    con.execute("SELECT COUNT(*) AS total FROM opportunities WHERE classification='HOT'").fetchone()["total"],
    con.execute("SELECT COUNT(*) AS total FROM opportunities WHERE classification='WARM'").fetchone()["total"],
]
con.close()

a,b,c,d,e = st.columns(5)
a.metric("Empresas", stats[0])
b.metric("Sinais", stats[1])
c.metric("Oportunidades", stats[2])
d.metric("HOT", stats[3])
e.metric("WARM", stats[4])

if st.button("🔎 IR PARA CAÇA", type="primary", use_container_width=True):
    with st.spinner("Executando caça real via fontes públicas..."):
        try:
            result = run_hunt()
            st.success(
                f"Caça #{result[0]} concluída — "
                f"{result[1]} fontes | {result[2]} sinais | {result[3]} empresas | "
                f"{result[4]} novas | {result[5]} atualizadas | {result[6]} descartadas."
            )
        except Exception as ex:
            st.error(f"Erro na caça: {ex}")

st.divider()
f = st.selectbox("Classificação", ["TODAS","HOT","WARM","WATCH","IGNORE"])

for o in opportunities():
    if f != "TODAS" and o["classification"] != f:
        continue

    icon = {"HOT":"🔥","WARM":"🟠","WATCH":"👁️","IGNORE":"⛔"}[o["classification"]]

    with st.container(border=True):
        x,y,z = st.columns([5,1,1])
        x.subheader(f"{icon} {o['name']}")
        x.caption(o["website"] or "")
        y.metric("Score", o["score"])
        z.metric("Confidence", o["confidence"])

        st.write(
            f"**ICP:** {o['icp']} | **Intent:** {o['intent']} | "
            f"**Need:** {o['need']} | **Pain/Risk:** {o['pain']} | "
            f"**Timing:** {o['timing']}"
        )
        st.write(
            f"**Trigger:** {o['trigger_text']} | **Decision Maker:** {o['dm']}"
        )
        st.write(f"**Próxima ação:** {o['next_action']}")

        with st.expander("Evidências rastreáveis"):
            st.write(o["reason"])
            for v in evidence(o["id"]):
                st.markdown(f"- **{v['kind']} / FACT:** {v['evidence']}")
                st.caption(
                    f"{v['title']} — {v['url']} | coletada {v['collected_at']}"
                )

st.divider()
st.subheader("Exportação")

data = []
for o in opportunities():
    evs = evidence(o["id"])
    for v in evs or [None]:
        data.append({
            "Company": o["name"], "Website": o["website"], "ICP Fit": o["icp"],
            "Business Trigger": o["trigger_text"], "Need Signal": o["need"],
            "Pain/Risk": o["pain"], "Buying Intent": o["intent"],
            "Decision Maker": o["dm"], "Timing": o["timing"],
            "Opportunity Score": o["score"], "Confidence": o["confidence"],
            "Classification": o["classification"], "Next Action": o["next_action"],
            "Source": v["title"] if v else "", "Source URL": v["url"] if v else "",
            "Evidence": v["evidence"] if v else "",
            "Collected Date": v["collected_at"] if v else ""
        })

df = pd.DataFrame(data)

st.download_button(
    "⬇️ Exportar CSV", df.to_csv(index=False).encode("utf-8-sig"),
    "hunter_techs.csv", "text/csv"
)

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Opportunities")

st.download_button(
    "⬇️ Exportar XLSX", buf.getvalue(), "hunter_techs.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
