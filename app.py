import streamlit as st
import sqlite3, re, requests, pandas as pd, io
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlparse

st.set_page_config(page_title="HUNTER TECHS", page_icon="🔎", layout="wide")

DB = "hunter.db"
HEADERS = {"User-Agent": "Mozilla/5.0 TECHS-Hunter/2.0"}

QUERIES = [
    '"RFP" "segurança da informação" Brasil',
    '"cotação" "segurança da informação" Brasil',
    '"solicitação de proposta" TI Brasil',
    '"contratação" "serviços gerenciados" TI Brasil',
    '"novo CIO" empresa Brasil',
    '"novo CTO" empresa Brasil',
    '"novo gerente de TI" empresa Brasil',
    '"migração para cloud" empresa Brasil',
    '"transformação digital" infraestrutura empresa Brasil',
]

TRIGGERS = ["novo cio","novo cto","novo diretor","novo gerente de ti","expansão",
"aquisição","nova unidade","nova filial","crescimento","transformação digital",
"migração","cloud","implantação de erp","incidente de segurança","reestruturação de ti"]
NEEDS = ["rmm","edr","backup","segurança","monitoramento","endpoint","firewall",
"sase","serviços gerenciados","infraestrutura","cloud","nuvem","cybersecurity",
"continuidade","governança"]
INTENTS = ["rfp","rfq","solicitação de proposta","cotação","busca de fornecedor",
"processo de contratação","contratação de serviço","troca de fornecedor",
"busca de parceiro","request for proposal","request for quotation"]
DMS = ["diretor de ti","diretor de tecnologia","cio","cto","gerente de ti"]

def now():
    return datetime.now().isoformat(timespec="seconds")

def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    # Compatibility check: an older hunter.db may have an incompatible schema.
    required = {
        "companies": {"id","name","website","icp","created_at","updated_at"},
        "sources": {"id","company_id","title","url","collected_at","content"},
        "signals": {"id","company_id","source_id","kind","evidence","evidence_type","created_at"},
        "opportunities": {"id","company_id","trigger_text","need","pain","intent","dm",
                          "timing","score","confidence","classification","next_action",
                          "reason","created_at","updated_at"},
        "hunts": {"id","started_at","finished_at","status","companies","new_opps",
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
      collected_at TEXT, content TEXT);

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
      companies INTEGER, new_opps INTEGER, updated_opps INTEGER, discarded INTEGER);
    """)
    c.commit()
    return c

def rss_search(query):
    """Uses public Google News RSS instead of scraping a search-result HTML page."""
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        items = []
        for item in soup.find_all("item"):
            title = item.title.get_text(" ", strip=True) if item.title else ""
            link = item.link.get_text(strip=True) if item.link else ""
            pub = item.pubDate.get_text(strip=True) if item.pubDate else ""
            source = item.source.get_text(" ", strip=True) if item.source else ""
            if link:
                items.append({"title": title, "url": link, "published": pub, "source": source})
        return items[:12]
    except Exception:
        return []

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for x in soup(["script","style","noscript"]):
            x.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        return title, text[:100000], r.url
    except Exception:
        return None, None, url

def hits(text, terms):
    t = (text or "").lower()
    return [x for x in terms if x in t]

def extract_company(title, text):
    # Prefer an explicit company-name pattern from the article title.
    if not title:
        return None
    parts = re.split(r"\s[-|–—:]\s", title)
    candidate = parts[0].strip()
    if 2 <= len(candidate.split()) <= 10 and len(candidate) <= 120:
        return candidate
    return None

def calculate(intent, need, pain, timing, dm):
    raw = 7
    raw += 25 if intent == "HIGH" else 0
    raw += 20 if need == "HIGH" else 0
    raw += 12 if pain == "MEDIUM" else 0
    raw += 10 if timing == "HIGH" else 0
    raw += 7 if dm == "LIKELY" else 0
    cap = {"NONE":30,"LOW":55,"MEDIUM":75,"HIGH":90,"VERY HIGH":100}[intent]
    return min(raw, cap)

def run_hunt():
    con = get_db()
    cur = con.cursor()
    cur.execute("INSERT INTO hunts(started_at,status) VALUES(?,?)", (now(), "RUNNING"))
    hunt_id = cur.lastrowid
    con.commit()

    urls = set()
    companies = set()
    new_opps = updated = discarded = 0

    try:
        for query in QUERIES:
            results = rss_search(query)
            for item in results:
                url = item["url"]
                if url in urls:
                    continue
                urls.add(url)

                title, text, final_url = fetch_page(url)
                if not text:
                    discarded += 1
                    continue

                name = extract_company(title, text)
                if not name:
                    # Keep the source even when company extraction is inconclusive,
                    # but do not manufacture an opportunity.
                    discarded += 1
                    continue

                companies.add(name)

                row = cur.execute(
                    "SELECT id FROM companies WHERE lower(name)=lower(?)", (name,)
                ).fetchone()

                if row:
                    cid = row["id"]
                    cur.execute(
                        "UPDATE companies SET website=?,updated_at=? WHERE id=?",
                        (final_url, now(), cid)
                    )
                else:
                    cur.execute(
                        "INSERT INTO companies(name,website,created_at,updated_at) VALUES(?,?,?,?)",
                        (name, final_url, now(), now())
                    )
                    cid = cur.lastrowid

                cur.execute(
                    """INSERT OR IGNORE INTO sources(company_id,title,url,collected_at,content)
                       VALUES(?,?,?,?,?)""",
                    (cid, title, final_url, now(), text[:30000])
                )
                sid = cur.execute(
                    "SELECT id FROM sources WHERE url=?", (final_url,)
                ).fetchone()["id"]

                tr = hits(text, TRIGGERS)
                ne = hits(text, NEEDS)
                it = hits(text, INTENTS)

                sentences = re.split(r"(?<=[.!?])\s+", text)
                evidence = [
                    s.strip() for s in sentences
                    if 35 <= len(s) <= 700
                    and any(k in s.lower() for k in TRIGGERS + NEEDS + INTENTS + DMS)
                ][:8]

                for ev in evidence:
                    kind = (
                        "BUYING_INTENT" if any(k in ev.lower() for k in INTENTS)
                        else "BUSINESS_TRIGGER" if any(k in ev.lower() for k in TRIGGERS)
                        else "NEED_SIGNAL"
                    )
                    cur.execute(
                        """INSERT OR IGNORE INTO signals
                           (company_id,source_id,kind,evidence,evidence_type,created_at)
                           VALUES(?,?,?,?,?,?)""",
                        (cid, sid, kind, ev, "FACT", now())
                    )

                intent = "HIGH" if it else "NONE"
                need = "HIGH" if ne else "NONE"
                pain = "MEDIUM" if tr and ne else "NONE"
                timing = "HIGH" if tr else "NONE"
                dm = "LIKELY" if any(k in text.lower() for k in DMS) else "NONE"
                sc = calculate(intent, need, pain, timing, dm)
                confidence = "HIGH" if it and ne else ("MEDIUM" if it or ne else "LOW")

                if not evidence:
                    classification = "IGNORE"
                elif sc >= 75 and intent == "HIGH":
                    classification = "HOT"
                elif sc >= 55 and intent in ("MEDIUM","HIGH","VERY HIGH"):
                    classification = "WARM"
                elif sc >= 30:
                    classification = "WATCH"
                else:
                    classification = "IGNORE"

                action = {
                    "HOT": "Abordar o decisor usando a evidência e validar a dor.",
                    "WARM": "Fazer abordagem consultiva e confirmar necessidade/intenção.",
                    "WATCH": "Monitorar novos sinais antes de abordagem.",
                    "IGNORE": "Não abordar; evidência insuficiente."
                }[classification]

                reason = (
                    f"ICP 7/15; Intent {25 if intent=='HIGH' else 0}/25; "
                    f"Need {20 if need=='HIGH' else 0}/20; "
                    f"Pain {12 if pain=='MEDIUM' else 0}/20; "
                    f"Timing {10 if timing=='HIGH' else 0}/10; "
                    f"DM {7 if dm=='LIKELY' else 0}/10."
                )

                old = cur.execute(
                    "SELECT id FROM opportunities WHERE company_id=?", (cid,)
                ).fetchone()

                cur.execute(
                    """INSERT INTO opportunities
                    (company_id,trigger_text,need,pain,intent,dm,timing,score,
                     confidence,classification,next_action,reason,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(company_id) DO UPDATE SET
                    trigger_text=excluded.trigger_text, need=excluded.need,
                    pain=excluded.pain, intent=excluded.intent, dm=excluded.dm,
                    timing=excluded.timing, score=excluded.score,
                    confidence=excluded.confidence, classification=excluded.classification,
                    next_action=excluded.next_action, reason=excluded.reason,
                    updated_at=excluded.updated_at""",
                    (
                        cid, tr[0] if tr else "UNKNOWN", need, pain, intent, dm,
                        timing, sc, confidence, classification, action, reason, now(), now()
                    )
                )

                if classification == "IGNORE":
                    discarded += 1
                elif old:
                    updated += 1
                else:
                    new_opps += 1
                con.commit()

        cur.execute(
            """UPDATE hunts SET finished_at=?,status=?,companies=?,new_opps=?,
               updated_opps=?,discarded=? WHERE id=?""",
            (now(),"COMPLETED",len(companies),new_opps,updated,discarded,hunt_id)
        )
        con.commit()
        return hunt_id, len(companies), new_opps, updated, discarded, len(urls)

    except Exception:
        cur.execute(
            "UPDATE hunts SET finished_at=?,status=? WHERE id=?",
            (now(),"FAILED",hunt_id)
        )
        con.commit()
        raise
    finally:
        con.close()

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
           FROM signals s JOIN sources src ON src.id=s.source_id
           JOIN opportunities o ON o.company_id=s.company_id
           WHERE o.id=? ORDER BY src.collected_at DESC""", (oid,)
    ).fetchall()
    con.close()
    return rows

st.title("🔎 HUNTER TECHS")
st.caption("Opportunity Intelligence Radar — CAÇA REAL")

con = get_db()
stats = [
    con.execute("SELECT COUNT(*) AS total FROM companies").fetchone()["total"],
    con.execute("SELECT COUNT(*) n FROM opportunities WHERE classification!='IGNORE'").fetchone()["n"],
    con.execute("SELECT COUNT(*) n FROM opportunities WHERE classification='HOT'").fetchone()["n"],
    con.execute("SELECT COUNT(*) n FROM opportunities WHERE classification='WARM'").fetchone()["n"],
]
con.close()

a,b,c,d = st.columns(4)
a.metric("Empresas", stats[0])
b.metric("Oportunidades", stats[1])
c.metric("HOT", stats[2])
d.metric("WARM", stats[3])

if st.button("🔎 IR PARA CAÇA", type="primary", use_container_width=True):
    with st.spinner("Executando caça real via fontes públicas..."):
        try:
            result = run_hunt()
            st.success(
                f"Caça #{result[0]} concluída — "
                f"{result[1]} empresas | {result[2]} novas | "
                f"{result[3]} atualizadas | {result[4]} descartadas | "
                f"{result[5]} fontes encontradas."
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
            f"**Need:** {o['need']} | **Timing:** {o['timing']}"
        )
        st.write(
            f"**Trigger:** {o['trigger_text']} | **Pain/Risk:** {o['pain']} | "
            f"**Decision Maker:** {o['dm']}"
        )
        st.write(f"**Próxima ação:** {o['next_action']}")

        with st.expander("Evidências"):
            st.write(o["reason"])
            for v in evidence(o["id"]):
                st.markdown(f"- **{v['kind']} / FACT:** {v['evidence']}")
                st.caption(f"{v['title']} — {v['url']} | coletada {v['collected_at']}")

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
