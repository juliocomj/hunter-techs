import io, re, sqlite3, hashlib
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# PHASE 1: Import new modules
try:
    from entity_resolver import EntityResolver, validate_company_name, clean_company, source_domain
    from signal_validator import (
        filter_signals, validate_buying_intent, classify_signal_type,
        extract_timeline, extract_specificity_signals, calculate_specificity_bonus,
        is_hiring_signal, has_negative_keywords
    )
    PHASE_1_ENABLED = True
except ImportError as e:
    print(f"⚠️  PHASE 1 modules not found: {e}")
    PHASE_1_ENABLED = False

st.set_page_config(page_title="HUNTER TECHS", page_icon="🔎", layout="wide")

DB = "hunter.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126 Safari/537.36 TECHS-Hunter/9.0"
}

# ============================================================
# MILO — broad market reading vocabulary
# ============================================================
SEARCH_QUERIES = [
    '"RFP" "segurança da informação"', '"RFQ" "segurança"',
    '"solicitação de proposta" "serviços de TI"', '"processo de contratação" "TI"',
    '"busca de fornecedor" tecnologia', '"seleção de fornecedor" TI',
    '"contratação" "serviços gerenciados"', '"contratação" "cibersegurança"',
    '"contratação" "backup" tecnologia', '"contratação" "monitoramento" TI',
    '"novo CIO" empresa', '"novo CTO" empresa', '"novo diretor de tecnologia"',
    '"novo diretor de TI"', '"novo gerente de TI"', '"head de tecnologia" empresa',
    '"migração para cloud" empresa', '"migração para nuvem" empresa',
    '"modernização da infraestrutura" empresa', '"transformação digital" empresa',
    '"projeto de infraestrutura" empresa', '"data center" expansão empresa',
    '"abriu novas unidades" empresa', '"novas lojas" expansão empresa',
    '"nova filial" empresa', '"aquisição" empresa tecnologia', '"fusão" empresa tecnologia',
    'ransomware empresa', '"incidente de segurança" empresa', '"ataque cibernético" empresa',
    '"vulnerabilidade" empresa segurança', '"vazamento de dados" empresa',
    '"monitoramento 24x7" empresa', '"continuidade de negócios" empresa tecnologia',
]

INTENT_STRONG = [
    "rfp", "rfq", "request for proposal", "request for quotation",
    "solicitação de proposta", "solicitação de cotação", "processo de contratação",
    "contratação de fornecedor", "busca de fornecedor", "busca por fornecedor",
    "seleção de fornecedor", "fornecedores interessados", "convidou fornecedores",
    "edital", "licitação", "pregão", "concorrência", "tomada de preços",
    "troca de fornecedor", "busca de parceiro", "contratação de empresa",
]
INTENT_CONTEXT = ["cotação", "orçamento", "comprar", "aquisição", "contratar"]
NEED_TERMS = [
    "rmm", "edr", "backup", "segurança da informação", "segurança cibernética",
    "cibersegurança", "cybersecurity", "monitoramento de infraestrutura", "monitoramento de ti",
    "gestão de endpoints", "endpoint", "firewall", "sase", "serviços gerenciados",
    "managed services", "infraestrutura de ti", "infraestrutura tecnológica", "cloud", "nuvem",
    "continuidade", "disaster recovery", "recuperação de desastre", "governança de ti",
    "observabilidade", "soc", "mssp", "backup em nuvem", "proteção de endpoints",
]
TRIGGER_TERMS = [
    "novo cio", "novo cto", "novo diretor de ti", "novo diretor de tecnologia",
    "novo gerente de ti", "head de tecnologia", "expansão", "nova unidade", "nova filial",
    "aquisição", "fusão", "crescimento", "transformação digital", "migração para cloud",
    "migração para nuvem", "implantação de erp", "incidente de segurança", "ataque cibernético",
    "reestruturação de ti", "modernização da infraestrutura", "novas lojas", "novas unidades",
    "data center", "novo centro de distribuição", "abertura de unidades",
]
PAIN_TERMS = [
    "indisponibilidade", "downtime", "parada", "falha", "incidente", "ataque", "vulnerabilidade",
    "risco", "interrupção", "perda de dados", "vazamento", "ransomware", "obsolescência",
    "falta de equipe", "sobrecarga", "24x7", "tempo de resposta", "indisponível",
]
DM_TERMS = [
    "cio", "cto", "diretor de ti", "diretor de tecnologia", "gerente de ti",
    "gerente de tecnologia", "head de tecnologia", "diretor de infraestrutura",
    "diretor de segurança", "chief information officer", "chief technology officer",
]
TECH_TERMS = set(NEED_TERMS + ["ti", "tecnologia", "infraestrutura", "segurança", "cloud", "dados"])

MEDIA_NAMES = {
    "google news", "google", "youtube", "facebook", "linkedin", "reuters", "exame", "valor",
    "estadao", "estadião", "folha", "globo", "uol", "terra", "cnn", "forbes", "g1",
    "canaltech", "tecmundo", "olhar digital", "infomoney", "istoé", "isto é", "news",
    "metropoles", "bloomberg", "moneytimes", "startups", "ti inside", "teletime", "convergencia digital",
}
MEDIA_DOMAINS = {
    "news.google.com", "g1.globo.com", "exame.com", "valor.globo.com", "uol.com.br", "terra.com.br",
    "estadao.com.br", "folha.uol.com.br", "oglobo.globo.com", "cnnbrasil.com.br", "forbes.com.br",
    "canaltech.com.br", "tecmundo.com.br", "olhardigital.com.br", "infomoney.com.br", "metropoles.com",
    "teletime.com.br", "convergenciadigital.com.br", "startups.com.br", "moneytimes.com.br",
}
LEGAL_SUFFIX = re.compile(r"\b(S\.?A\.?|S/A|LTDA|Ltda\.?|Holding|Holdings|Corp\.?|Inc\.?|Group|Grupo)\b", re.I)


def now():
    return datetime.now().isoformat(timespec="seconds")


def norm(x):
    return re.sub(r"\s+", " ", (x or "")).strip()


def term_hits(text, terms):
    low = (text or "").lower()
    return [t for t in terms if t in low]


def valid_company(name):
    if not name:
        return False
    n = norm(name).strip(" -–—:,.()[]\"'")
    low = n.lower()
    if low in MEDIA_NAMES or any(low.startswith(x + " ") for x in MEDIA_NAMES):
        return False
    if len(n) < 3 or len(n) > 110 or len(n.split()) > 10:
        return False
    if re.fullmatch(r"[0-9 .,%/-]+", n):
        return False
    bad = {"empresa", "companhia", "grupo", "organização", "organizacao", "tecnologia", "segurança", "infraestrutura"}
    if low in bad:
        return False
    return True


def clean_company_old(c):
    c = norm(c).strip(" -–—:,.()[]\"'")
    m = re.search(r"\s+[AaOo]\s+(?:Empresa|Grupo|Companhia|Holding)\b", c)
    if m:
        c = c[:m.start()]
    c = re.sub(r"^(?:a|o|as|os|da|do|na|no)\s+", "", c, flags=re.I)
    c = re.sub(r"\s+(?:anuncia|anunciou|contrata|contratou|busca|buscou|expande|expandiu|abre|abriu|projeta|prevê|preve|investe|investiu|vai|inicia|iniciou).*$", "", c, flags=re.I)
    return c.strip(" -–—:,.()[]\"'")


def extract_company(title, body, publisher, explicit_candidate=None, url=""):
    """PHASE 1: Enhanced entity resolution with spaCy fallback"""
    
    # Use PHASE 1 resolver if available
    if PHASE_1_ENABLED:
        try:
            # Get existing companies for dedup
            c = sqlite3.connect(DB)
            existing = c.execute("SELECT id, name, website FROM companies LIMIT 500").fetchall()
            existing_list = [{'name': e[1], 'website': e[2]} for e in existing]
            c.close()
            
            resolver = EntityResolver(existing_list)
            company = resolver.resolve_company(title, body, publisher, url, explicit_candidate)
            return company
        except Exception as e:
            print(f"⚠️  PHASE 1 resolver error: {e}, falling back to legacy")
    
    # Fallback to original logic
    candidates = []
    def add(c, weight=0):
        c = clean_company_old(c)
        if valid_company(c) and c.lower() != (publisher or "").lower() and c.lower() not in {x[0].lower() for x in candidates}:
            candidates.append((c, weight))

    if explicit_candidate:
        add(explicit_candidate, 100)

    t = norm(title)
    b = norm(body)
    h = t + " " + b[:8000]

    verb = r"(?:anuncia|anunciou|contrata|contratou|busca|buscou|expande|expandiu|abre|abriu|projeta|prevê|preve|investe|investiu|inicia|iniciou|adota|adotou|lança|lancou|lançou|moderniza|modernizou)"
    for m in re.finditer(rf"^(.{{3,100}}?)\s+{verb}\b", t, flags=re.I):
        add(m.group(1), 90)
    for m in re.finditer(r"^(.{3,90}?)\s*[:–—-]\s+", t):
        add(m.group(1), 70)

    verb_words = r"(?:anuncia|anunciou|contrata|contratou|busca|buscou|expande|expandiu|abre|abriu|projeta|prevê|preve|investe|investiu|inicia|iniciou|adota|adotou|lança|lancou|lançou|moderniza|modernizou)"
    for m in re.finditer(
        rf"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9&.'/-]*){{0,6}})\s+{verb_words}\b",
        h
    ):
        add(m.group(1), 65)

    first = (t + " " + b[:2500])
    for m in re.finditer(r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç0-9&.'/-]*(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç0-9&.'/-]*){{0,6}})\b", first):
        c = m.group(1)
        low = c.lower()
        if low not in {"novo", "nova", "empresa", "grupo", "brasil", "são paulo", "rio de janeiro"}:
            weight = 35 + (20 if LEGAL_SUFFIX.search(c) else 0)
            add(c, weight)

    dom = source_domain(url) if source_domain else urlparse(url).netloc.lower().replace("www.", "")
    if dom and dom not in MEDIA_DOMAINS and not any(x in dom for x in ["gov.br", "jus.br", "leg.br"]):
        root = dom.split(".")[0]
        if len(root) >= 4 and root not in MEDIA_NAMES and root not in {"www", "blog", "portal", "site"}:
            add(root.replace("-", " ").title(), 20)

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[1], len(x[0])))
    return candidates[0][0]


def evidence_snippets(text, terms, max_items=4):
    """Find context windows, not only full sentences; avoids losing RSS snippets."""
    text = norm(text)
    low = text.lower()
    out = []
    for term in sorted(set(terms), key=len, reverse=True):
        start = 0
        while True:
            i = low.find(term, start)
            if i < 0:
                break
            a = max(0, i - 220)
            z = min(len(text), i + len(term) + 320)
            snippet = norm(text[a:z]).strip(" -–—")
            if len(snippet) >= 45 and snippet.lower() not in {x.lower() for x in out}:
                out.append(snippet)
            start = i + len(term)
            if len(out) >= max_items:
                return out
    return out


def classify_company(signals):
    """PHASE 1: Enhanced classification with signal validation"""
    
    # NEW: Filter out hiring signals and negative keywords
    if PHASE_1_ENABLED:
        try:
            filtered_signals = filter_signals(signals)
            if not filtered_signals:
                return "NONE", "NONE", "NONE", "NONE", "NONE", 0, "LOW", "IGNORE"
            signals = filtered_signals
        except Exception as e:
            print(f"⚠️  Signal filtering error: {e}")
    
    by = {}
    for s in signals:
        by.setdefault(s["kind"], []).append(s)
    
    intent_strong = len(by.get("BUYING_INTENT", []))
    need_n = len(by.get("NEED_SIGNAL", []))
    pain_n = len(by.get("PAIN_RISK", []))
    trigger_n = len(by.get("BUSINESS_TRIGGER", []))
    dm_n = len(by.get("DECISION_MAKER", []))

    if intent_strong >= 3: intent = "VERY HIGH"
    elif intent_strong >= 2: intent = "HIGH"
    elif intent_strong >= 1: intent = "MEDIUM"
    else: intent = "NONE"
    need = "HIGH" if need_n >= 2 else ("MEDIUM" if need_n == 1 else "NONE")
    pain = "HIGH" if pain_n >= 2 else ("MEDIUM" if pain_n == 1 else "NONE")
    timing = "HIGH" if trigger_n >= 2 else ("MEDIUM" if trigger_n == 1 else "NONE")
    dm = "LIKELY" if dm_n else "NONE"

    # NEW: Specificity bonus from PHASE 1
    specificity_bonus = 0
    if PHASE_1_ENABLED:
        try:
            specificity_bonus = calculate_specificity_bonus(signals)
        except Exception:
            pass

    # TECHS Engine V1.1 — conservative, with ICP unknown until evidence exists.
    score = 7
    score += {"NONE":0, "MEDIUM":6, "HIGH":15, "VERY HIGH":25}[intent]
    score += {"NONE":0, "MEDIUM":10, "HIGH":20}[need]
    score += {"NONE":0, "MEDIUM":10, "HIGH":20}[pain]
    score += {"NONE":0, "MEDIUM":5, "HIGH":10}[timing]
    score += 7 if dm == "LIKELY" else 0
    score += specificity_bonus  # NEW: Add specificity bonus
    score = min(score, {"NONE":30, "MEDIUM":75, "HIGH":90, "VERY HIGH":100}[intent])

    # NEW: Require NEED or PAIN for WARM+ classification
    if intent == "VERY HIGH" and need != "NONE" and score >= 75:
        cls = "HOT"
    elif intent in ("HIGH", "VERY HIGH") and need != "NONE" and score >= 55:
        cls = "WARM"
    elif need != "NONE" or pain != "NONE" or intent != "NONE":
        cls = "WATCH"
    else:
        cls = "IGNORE"
    
    confidence = "HIGH" if intent in ("HIGH", "VERY HIGH") and need != "NONE" else ("MEDIUM" if need != "NONE" or pain != "NONE" or intent != "NONE" else "LOW")
    return intent, need, pain, timing, dm, score, confidence, cls


def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS companies(
      id INTEGER PRIMARY KEY, name TEXT UNIQUE, website TEXT, icp TEXT DEFAULT 'UNKNOWN',
      created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS sources(
      id INTEGER PRIMARY KEY, company_id INTEGER NULL, title TEXT, url TEXT UNIQUE,
      source_type TEXT DEFAULT 'NOTICIA', publisher TEXT, collected_at TEXT, content TEXT,
      published_at TEXT, query TEXT);
    CREATE TABLE IF NOT EXISTS signals(
      id INTEGER PRIMARY KEY, company_id INTEGER NULL, source_id INTEGER NULL, kind TEXT,
      evidence TEXT, evidence_type TEXT, confidence TEXT DEFAULT 'MEDIUM', created_at TEXT,
      UNIQUE(source_id,kind,evidence));
    CREATE TABLE IF NOT EXISTS opportunities(
      id INTEGER PRIMARY KEY, company_id INTEGER UNIQUE, trigger_text TEXT, need TEXT, pain TEXT,
      intent TEXT, dm TEXT, timing TEXT, score INTEGER, confidence TEXT, classification TEXT,
      next_action TEXT, reason TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS hunts(
      id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT,
      sources_found INTEGER DEFAULT 0, signals_found INTEGER DEFAULT 0, companies INTEGER DEFAULT 0,
      new_opps INTEGER DEFAULT 0, updated_opps INTEGER DEFAULT 0, discarded INTEGER DEFAULT 0,
      unassigned_signals INTEGER DEFAULT 0);
    """)
    # Migrations for older V8 DBs.
    for table, col, typ in [
        ("signals", "confidence", "TEXT DEFAULT 'MEDIUM'"),
        ("sources", "published_at", "TEXT"), ("sources", "query", "TEXT"),
        ("hunts", "unassigned_signals", "INTEGER DEFAULT 0")]:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

    # Remove only known media-as-company corruption; preserve all legitimate signals.
    for name in MEDIA_NAMES:
        c.execute("DELETE FROM opportunities WHERE company_id IN (SELECT id FROM companies WHERE lower(name)=?)", (name,))
        c.execute("DELETE FROM signals WHERE company_id IN (SELECT id FROM companies WHERE lower(name)=?)", (name,))
        c.execute("DELETE FROM sources WHERE company_id IN (SELECT id FROM companies WHERE lower(name)=?)", (name,))
        c.execute("DELETE FROM companies WHERE lower(name)=?", (name,))
    c.commit()
    return c


def rss_search(query):
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        out = []
        for item in soup.find_all("item"):
            link = item.link.get_text(strip=True) if item.link else ""
            if not link: continue
            out.append({
                "title": norm(item.title.get_text(" ", strip=True) if item.title else ""),
                "url": link,
                "description": norm(BeautifulSoup(item.description.get_text(" ", strip=True), "html.parser").get_text(" ", strip=True) if item.description else ""),
                "published": norm(item.pubDate.get_text(" ", strip=True) if item.pubDate else ""),
                "publisher": norm(item.source.get_text(" ", strip=True) if item.source else ""),
                "source_type": "NEWS",
                "query": query,
            })
        return out[:20]
    except Exception:
        return []


def pncp_search(pages=6, days_forward=30):
    """Open public PNCP consultation. Proposals open are high-value buying-intent evidence."""
    base = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
    final = (datetime.now() + timedelta(days=days_forward)).strftime("%Y%m%d")
    out = []
    for page in range(1, pages + 1):
        try:
            r = requests.get(base, params={"dataFinal": final, "pagina": page, "tamanhoPagina": 50}, headers=HEADERS, timeout=25)
            r.raise_for_status()
            payload = r.json()
            rows = payload.get("data") or payload.get("resultado") or []
            if not rows: break
            for row in rows:
                org = norm(row.get("orgaoEntidade", {}).get("razaoSocial") if isinstance(row.get("orgaoEntidade"), dict) else row.get("orgaoEntidade") or row.get("nomeOrgao") or "")
                obj = norm(row.get("objetoCompra") or row.get("objeto") or row.get("descricao") or "")
                ctrl = norm(row.get("numeroControlePNCP") or "")
                link = norm(row.get("linkSistemaOrigem") or "")
                if not link and ctrl: link = "https://pncp.gov.br/app/editais/" + ctrl
                if not link: link = "https://pncp.gov.br/"
                out.append({
                    "title": norm((org + " �� " + obj)[:500]), "url": link,
                    "description": obj, "published": norm(row.get("dataPublicacaoPncp") or ""),
                    "publisher": "PNCP", "source_type": "PNCP", "company_candidate": org,
                    "query": "PNCP propostas abertas"
                })
        except Exception:
            break
    return out


def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=18, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for x in soup(["script", "style", "noscript", "svg"]): x.decompose()
        title = norm(soup.title.get_text(" ", strip=True) if soup.title else "")
        text = norm(soup.get_text(" ", strip=True))
        return title, text[:120000], r.url
    except Exception:
        return None, None, url


def find_or_create_company(cur, name, website):
    if not valid_company(name): return None
    name = clean_company_old(name)
    row = cur.execute("SELECT id FROM companies WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        cid = row["id"]
        if website: cur.execute("UPDATE companies SET website=?,updated_at=? WHERE id=?", (website, now(), cid))
        return cid
    # Domain-level merge: same company site, different article-derived spelling.
    dom = source_domain(website) if source_domain else (urlparse(website).netloc.lower().replace("www.", "") if website else "")
    if dom and dom not in MEDIA_DOMAINS:
        for r in cur.execute("SELECT id,website FROM companies WHERE website IS NOT NULL").fetchall():
            company_dom = source_domain(r["website"]) if source_domain else (urlparse(r["website"]).netloc.lower().replace("www.", "") if r["website"] else "")
            if company_dom == dom and dom:
                cur.execute("UPDATE companies SET updated_at=? WHERE id=?", (now(), r["id"]))
                return r["id"]
    cur.execute("INSERT INTO companies(name,website,icp,created_at,updated_at) VALUES(?,?,?,?,?)", (name, website or "", "UNKNOWN", now(), now()))
    return cur.lastrowid


def qualify_hunter(cur):
    rows = cur.execute("""
        SELECT c.id,c.name,c.website,c.icp,s.kind,s.evidence,s.confidence
        FROM companies c JOIN signals s ON s.company_id=c.id
        ORDER BY c.id,s.created_at DESC
    """).fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["id"], {"id":r["id"],"name":r["name"],"website":r["website"],"icp":r["icp"],"signals":[]})["signals"].append(dict(r))
    created = updated = 0
    for cid, item in by.items():
        intent,need,pain,timing,dm,score,conf,cls = classify_company(item["signals"])
        # Trigger alone is not an opportunity. Need, pain or intent must exist.
        if need == "NONE" and pain == "NONE" and intent == "NONE":
            cls = "IGNORE"
        groups = {}
        for s in item["signals"]: groups.setdefault(s["kind"], []).append(s["evidence"])
        trigger_text = " | ".join(groups.get("BUSINESS_TRIGGER", [])[:3]) or "Não identificado"
        need_text = " | ".join(groups.get("NEED_SIGNAL", [])[:3]) or "Não confirmado"
        pain_text = " | ".join(groups.get("PAIN_RISK", [])[:3]) or "Não confirmado"
        reason = "\n".join(f"{k}: {' | '.join(v[:3])}" for k,v in groups.items() if v)
        action = {
            "HOT":"Abordar decisor rapidamente e validar processo de compra.",
            "WARM":"Abordagem consultiva e validação da necessidade.",
            "WATCH":"Monitorar novos sinais antes de abordagem comercial.",
            "IGNORE":"Não abordar; aguardar evidência adicional."
        }[cls]
        exists = cur.execute("SELECT id FROM opportunities WHERE company_id=?", (cid,)).fetchone()
        vals=(trigger_text,need_text,pain_text,intent,dm,timing,score,conf,cls,action,reason,now())
        if exists:
            cur.execute("""UPDATE opportunities SET trigger_text=?,need=?,pain=?,intent=?,dm=?,timing=?,score=?,confidence=?,classification=?,next_action=?,reason=?,updated_at=? WHERE company_id=?""", vals + (cid,))
            updated += 1
        else:
            cur.execute("""INSERT INTO opportunities(company_id,trigger_text,need,pain,intent,dm,timing,score,confidence,classification,next_action,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (cid,) + vals)
            created += 1
    return created,updated


def run_hunt():
    con=get_db(); cur=con.cursor()
    cur.execute("INSERT INTO hunts(started_at,status) VALUES(?,?)", (now(),"RUNNING")); hid=cur.lastrowid; con.commit()
    raw=[]; seen=set(); sources_found=signals_found=unassigned=0
    try:
        # ---------- MILO COLLECTOR ----------
        for q in SEARCH_QUERIES:
            for item in rss_search(q):
                if item["url"] not in seen:
                    seen.add(item["url"]); raw.append(item)
        for item in pncp_search():
            key=item["url"]+"|"+item["title"][:120]
            if key not in seen:
                seen.add(key); raw.append(item)
        sources_found=len(raw)

        # Candidate gate is broad. It decides what Milo reads, not what Hunter buys.
        candidates=[]
        for item in raw:
            meta=norm(item.get("title","")+" "+item.get("description",""))
            hits=set(term_hits(meta,INTENT_STRONG+INTENT_CONTEXT+NEED_TERMS+TRIGGER_TERMS+PAIN_TERMS+DM_TERMS))
            if hits or item.get("source_type")=="PNCP":
                candidates.append((len(hits)+(5 if item.get("source_type")=="PNCP" else 0),item))
        candidates.sort(key=lambda x:-x[0])

        # Enrich more sources than V8 while keeping Streamlit responsive.
        for _, item in candidates[:450]:
            desc=item.get("description","")
            page_title,page_text,final_url=fetch_page(item.get("url", ""))
            title=page_title or item.get("title","")
            body=page_text or desc
            combined=norm(title+" "+desc+" "+body)
            company=extract_company(title,body,item.get("publisher",""),item.get("company_candidate"),final_url)
            cid=find_or_create_company(cur,company,final_url) if company else None

            # Save source even when entity resolution fails: it remains part of Milo's evidence trail.
            cur.execute("""INSERT INTO sources(company_id,title,url,source_type,publisher,collected_at,content,published_at,query)
                           VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET company_id=COALESCE(excluded.company_id,sources.company_id),
                           title=excluded.title,publisher=excluded.publisher,collected_at=excluded.collected_at,content=excluded.content,
                           published_at=excluded.published_at,query=excluded.query""",
                        (cid,title,final_url,item.get("source_type","NEWS"),item.get("publisher",""),now(),body[:50000],item.get("published",""),item.get("query","")))
            sid=cur.execute("SELECT id FROM sources WHERE url=?",(final_url,)).fetchone()["id"]

            # Intent: strong terms are enough only when the source also has TECH context;
            # generic "cotação/orçamento" is not automatically intent.
            intent_terms = INTENT_STRONG.copy()
            if term_hits(combined, INTENT_CONTEXT) and term_hits(combined, list(TECH_TERMS)):
                intent_terms += INTENT_CONTEXT
            signal_defs=[
                ("BUYING_INTENT",intent_terms),
                ("NEED_SIGNAL",NEED_TERMS),
                ("BUSINESS_TRIGGER",TRIGGER_TERMS),
                ("PAIN_RISK",PAIN_TERMS),
                ("DECISION_MAKER",DM_TERMS),
            ]
            for kind,terms in signal_defs:
                for ev in evidence_snippets(combined,terms,4):
                    # NEW: Check hiring signals and reject
                    if PHASE_1_ENABLED and kind == "BUYING_INTENT" and is_hiring_signal(ev):
                        continue  # Skip hiring signals
                    
                    # NEW: Check negative keywords
                    if PHASE_1_ENABLED and has_negative_keywords(ev):
                        continue  # Skip negative signals
                    
                    # Milo confidence is evidence confidence, not opportunity confidence.
                    conf="HIGH" if item.get("source_type")=="PNCP" and kind=="BUYING_INTENT" else "MEDIUM"
                    exists=cur.execute("SELECT id FROM signals WHERE source_id=? AND kind=? AND evidence=?",(sid,kind,ev)).fetchone()
                    if not exists:
                        cur.execute("INSERT INTO signals(company_id,source_id,kind,evidence,evidence_type,confidence,created_at) VALUES(?,?,?,?,?,?,?)",
                                    (cid,sid,kind,ev,"FACT",conf,now()))
                        signals_found += 1
                        if cid is None: unassigned += 1
            con.commit()

        # ---------- HUNTER ----------
        new_opps,updated=qualify_hunter(cur)
        companies=cur.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        unassigned_total=cur.execute("SELECT COUNT(*) FROM signals WHERE company_id IS NULL").fetchone()[0]
        cur.execute("""UPDATE hunts SET finished_at=?,status=?,sources_found=?,signals_found=?,companies=?,new_opps=?,updated_opps=?,discarded=?,unassigned_signals=? WHERE id=?""",
                    (now(),"COMPLETED",sources_found,signals_found,companies,new_opps,updated,unassigned_total,unassigned,hid))
        con.commit()
        return hid,sources_found,signals_found,companies,new_opps,updated,unassigned_total,unassigned
    except Exception as e:
        cur.execute("UPDATE hunts SET finished_at=?,status=? WHERE id=?",(now(),"FAILED",hid)); con.commit(); raise
    finally:
        con.close()


def opportunities():
    c=get_db(); rows=c.execute("""SELECT o.*,c.name,c.website,c.icp FROM opportunities o JOIN companies c ON c.id=o.company_id ORDER BY o.score DESC,o.updated_at DESC""").fetchall(); c.close(); return [dict(r) for r in rows]


def all_signals():
    c=get_db(); rows=c.execute("""SELECT s.*,c.name AS company,src.title,src.url,src.source_type,src.publisher,src.collected_at FROM signals s LEFT JOIN companies c ON c.id=s.company_id LEFT JOIN sources src ON src.id=s.source_id ORDER BY s.created_at DESC""").fetchall(); c.close(); return [dict(r) for r in rows]


def evidence(oid):
    c=get_db(); rows=c.execute("""SELECT s.kind,s.evidence,s.confidence,src.title,src.url,src.collected_at,src.source_type FROM signals s JOIN sources src ON src.id=s.source_id JOIN opportunities o ON o.id=? WHERE s.company_id=o.company_id ORDER BY s.created_at DESC""", (oid,)).fetchall(); c.close(); return [dict(r) for r in rows]

# ============================================================
# UI
# ============================================================
st.title("🔎 HUNTER TECHS")
status_msg = "PHASE 1 ATIVO ✅" if PHASE_1_ENABLED else "⚠️ PHASE 1 Offline (legacy mode)"
st.caption(f"Opportunity Intelligence Radar — CAÇA REAL • V9 + PHASE 1 — {status_msg}")

c=get_db()
stats=[
    c.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM signals").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM opportunities WHERE classification!='IGNORE'").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM opportunities WHERE classification='HOT'").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM opportunities WHERE classification='WARM'").fetchone()[0],
]
c.close()
a,b,d,e,f=st.columns(5)
a.metric("Empresas",stats[0]); b.metric("Sinais",stats[1]); d.metric("Oportunidades",stats[2]); e.metric("HOT",stats[3]); f.metric("WARM",stats[4])

if st.button("🔎 IR PARA CAÇA",type="primary",use_container_width=True):
    with st.spinner("Milo lendo fontes públicas e Hunter peneirando evidências..."):
        try:
            r=run_hunt()
            st.success(f"Caça #{r[0]} concluída — {r[1]} fontes | {r[2]} sinais novos | {r[3]} empresas | {r[4]} novas oportunidades | {r[5]} atualizadas | {r[6]} sinais sem empresa")
        except Exception as ex:
            st.error(f"Erro na caça: {ex}")

st.divider()
view=st.radio("Visão",["Oportunidades","Sinais do Milo"],horizontal=True)
if view=="Oportunidades":
    filt=st.selectbox("Classificação",["TODAS","HOT","WARM","WATCH","IGNORE"])
    for o in opportunities():
        if filt!="TODAS" and o["classification"]!=filt: continue
        icon={"HOT":"🔥","WARM":"🟠","WATCH":"👁️","IGNORE":"⛔"}[o["classification"]]
        with st.container(border=True):
            x,y,z=st.columns([6,1,1]); x.subheader(f"{icon} {o['name']}"); x.caption(o["website"] or "")
            y.metric("Score",o["score"]); z.metric("Confidence",o["confidence"])
            st.write(f"**ICP:** {o['icp']} | **Intent:** {o['intent']} | **Need:** {o['need']} | **Pain/Risk:** {o['pain']} | **Timing:** {o['timing']} | **DM:** {o['dm']}")
            st.write(f"**Próxima ação:** {o['next_action']}")
            with st.expander("Evidências rastreáveis"):
                st.write(o["reason"])
                for v in evidence(o["id"]):
                    st.markdown(f"- **{v['kind']} / {v['confidence']}:** {v['evidence']}")
                    st.caption(f"{v['title']} — {v['url']} | {v['source_type']} | {v['collected_at']}")
else:
    sigs=all_signals()
    st.caption(f"Milo estruturou {len(sigs)} sinais. Sinais sem empresa continuam armazenados e não viram oportunidade automaticamente.")
    for s in sigs[:400]:
        with st.container(border=True):
            company=s["company"] or "Empresa ainda não resolvida"
            x,y=st.columns([6,1]); x.markdown(f"**{company}** — `{s['kind']}`"); y.caption(s["source_type"] or "")
            st.write(s["evidence"])
            st.caption(f"{s['title']} | {s['url']} | {s['collected_at']}")

st.divider(); st.subheader("Exportação")
rows=[]
for o in opportunities():
    evs=evidence(o["id"])
    for v in evs or [None]:
        rows.append({"Company":o["name"],"Website":o["website"],"ICP Fit":o["icp"],"Business Trigger":o["trigger_text"],"Need Signal":o["need"],"Pain/Risk":o["pain"],"Buying Intent":o["intent"],"Decision Maker":o["dm"],"Score":o["score"]})
df=pd.DataFrame(rows)
st.download_button("⬇️ Exportar CSV",df.to_csv(index=False).encode("utf-8-sig"),"hunter_techs.csv","text/csv")
sigrows=[]
for s in all_signals(): sigrows.append({"Company":s["company"] or "","Signal Type":s["kind"],"Evidence":s["evidence"],"Confidence":s["confidence"],"Source Type":s["source_type"] or "","Source":s["title"] or ""})
sdf=pd.DataFrame(sigrows)
st.download_button("⬇️ Exportar sinais do Milo CSV",sdf.to_csv(index=False).encode("utf-8-sig"),"hunter_techs_milo_signals.csv","text/csv")
buf=io.BytesIO()
with pd.ExcelWriter(buf,engine="openpyxl") as w:
    df.to_excel(w,index=False,sheet_name="Opportunities"); sdf.to_excel(w,index=False,sheet_name="Milo_Signals")
st.download_button("⬇️ Exportar XLSX",buf.getvalue(),"hunter_techs.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
