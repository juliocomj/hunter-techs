import re
import sqlite3
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="HUNTER TECHS", page_icon="🔎", layout="wide")

DB = "hunter.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
}
MAX_DAYS = 5
HOT_DAYS = 3

# ============================================================
# HUNTER V12 — HOT SOURCE HUNTER
# Regra central: empresa privada + dor atual + evidência + intent.
# Governo/licitação não participa da caça comercial.
# ============================================================

SEARCH_QUERIES = [
    # BUYING INTENT — prioridade máxima
    '"RFP" "segurança da informação" empresa -gov -gov.br -prefeitura -licitação',
    '"RFQ" TI empresa fornecedor -gov -gov.br -licitação',
    '"request for proposal" cybersecurity company Brazil -government',
    '"request for quotation" IT company Brazil -government',
    '"buscando fornecedor" TI empresa -gov -licitação',
    '"busca de fornecedor" segurança empresa -gov -licitação',
    '"seleção de fornecedor" tecnologia empresa -gov -licitação',
    '"procura fornecedor" infraestrutura TI empresa -gov -licitação',
    '"serviços gerenciados" "fornecedor" empresa TI -gov',
    '"MSSP" "fornecedor" empresa -gov',
    '"SOC" "fornecedor" empresa segurança -gov',
    '"backup" "fornecedor" empresa TI -gov',
    '"firewall" "fornecedor" empresa -gov',
    '"monitoramento 24x7" "fornecedor" empresa -gov',
    # PAIN / INCIDENTE — últimos dias
    'empresa ransomware infraestrutura TI -gov -gov.br',
    'empresa "ataque cibernético" sistemas -gov -gov.br',
    'empresa "incidente de segurança" TI -gov -gov.br',
    'empresa "vazamento de dados" sistemas -gov -gov.br',
    'empresa "indisponibilidade" sistemas TI -gov -gov.br',
    'empresa "falha de infraestrutura" TI -gov -gov.br',
    'empresa "perda de dados" TI -gov -gov.br',
    'empresa vulnerabilidade infraestrutura segurança -gov -gov.br',
    'empresa "interrupção" sistemas tecnologia -gov -gov.br',
    # PRESSÃO OPERACIONAL / CONTINUIDADE
    'empresa "sobrecarga" "equipe de TI" -gov',
    'empresa "falta de equipe" TI segurança -gov',
    'empresa "continuidade de negócios" infraestrutura TI -gov',
    'empresa "disaster recovery" infraestrutura -gov',
    # TRIGGERS RECENTES QUE PODEM GERAR DEMANDA
    'empresa "novo CIO" infraestrutura -gov',
    'empresa "novo CTO" infraestrutura -gov',
    'empresa "novo diretor de TI" -gov',
    'empresa "migração para nuvem" infraestrutura -gov',
    'empresa "modernização da infraestrutura" TI -gov',
    'empresa "expansão" "infraestrutura de TI" -gov',
    'empresa "novas unidades" infraestrutura TI -gov',
    'empresa aquisição "infraestrutura de TI" -gov',
    'empresa fusão "infraestrutura de TI" -gov',
]

INTENT_STRONG = [
    "rfp", "rfq", "request for proposal", "request for quotation",
    "solicitação de proposta", "solicitacao de proposta",
    "pedido de cotação", "pedido de cotacao",
    "busca de fornecedor", "buscando fornecedor", "procura fornecedor",
    "seleção de fornecedor", "selecao de fornecedor", "vendor selection",
    "supplier search", "vendor change", "procura por fornecedor",
    "cotação de fornecedor", "cotacao de fornecedor",
]
INTENT_CONTEXT = ["cotação", "cotacao", "orçamento", "orcamento", "comprar", "contratar", "contratação", "contratacao", "fornecedor", "parceiro"]
TECH_TERMS = [
    "rmm", "edr", "xdr", "backup", "monitoramento", "monitorização", "endpoint", "endpoints",
    "firewall", "sase", "soc", "mssp", "segurança da informação", "seguranca da informacao",
    "cibersegurança", "ciberseguranca", "cybersecurity", "infraestrutura de ti", "infraestrutura",
    "serviços gerenciados", "servicos gerenciados", "cloud", "nuvem", "disaster recovery",
    "continuidade de negócios", "continuidade de negocios", "gestão de ti", "gestao de ti",
]
TRIGGER_TERMS = [
    "novo cio", "novo cto", "novo diretor de ti", "novo gerente de ti", "expansão", "expansao",
    "aquisição", "aquisicao", "fusão", "fusao", "transformação digital", "transformacao digital",
    "migração para nuvem", "migracao para nuvem", "modernização", "modernizacao", "novas unidades",
    "novas lojas", "abertura de lojas", "data center", "incidente de segurança", "incidente de seguranca",
]
PAIN_TERMS = [
    "downtime", "indisponibilidade", "falha de infraestrutura", "falha", "falhas", "ataque",
    "ransomware", "vulnerabilidade", "interrupção", "interrupcao", "perda de dados", "data loss",
    "incidente de segurança", "incidente de seguranca", "sobrecarga", "falta de equipe", "equipe reduzida",
]
DM_TERMS = [
    "cio", "cto", "ciso", "diretor de ti", "diretor de tecnologia", "gerente de ti",
    "gerente de tecnologia", "head de tecnologia", "head of technology", "diretor de segurança",
    "diretor de infraestrutura", "it manager",
]

MEDIA_DOMAINS = {
    "news.google.com", "google.com", "g1.globo.com", "oglobo.globo.com", "exame.com",
    "valor.globo.com", "estadao.com.br", "folha.uol.com.br", "uol.com.br", "terra.com.br",
    "cnnbrasil.com.br", "forbes.com", "reuters.com", "bloomberg.com", "infomoney.com.br",
    "canaltech.com.br", "tecmundo.com.br", "olhardigital.com.br", "itforum.com.br",
    "convergenciadigital.com.br", "prnewswire.com", "startse.com",
}
GOV_DOMAINS = {
    "gov.br", "pncp.gov.br", "compras.gov.br", "tcu.gov.br", "bcb.gov.br", "jus.br", "leg.br",
    "camara.leg.br", "senado.leg.br", "tce.sp.gov.br", "tce.rj.gov.br",
}
GOV_TERMS = [
    "governo federal", "órgão público", "orgao publico", "prefeitura", "município", "municipio",
    "ministério", "ministerio", "secretaria de estado", "tribunal de contas", "tcu", "pncp",
    "licitação", "licitacao", "edital", "pregão", "pregao", "dispensa de licitação",
    "compras públicas", "compras publicas", "contratação pública", "contratacao publica",
]
GENERIC_NAMES = {
    "empresa", "companhia", "organização", "organizacao", "grupo", "cliente", "fornecedor",
    "governo", "prefeitura", "estado", "município", "municipio", "brasil", "mercado", "setor",
}

# ============================================================
# UTILITÁRIOS
# ============================================================

def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def clean_text(s):
    return norm(BeautifulSoup(str(s or ""), "html.parser").get_text(" ", strip=True))

def source_domain(url):
    try:
        host = (urlparse(url).netloc or "").lower().split(":")[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

def has_term(text, term):
    t = str(term).lower().strip()
    if not t:
        return False
    if len(t) <= 3:
        return bool(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", str(text or "").lower()))
    return t in str(text or "").lower()

def term_hits(text, terms):
    return [t for t in terms if has_term(text, t)]

def is_media(url):
    host = source_domain(url)
    return host in MEDIA_DOMAINS or any(host.endswith("." + d) for d in MEDIA_DOMAINS)

def is_government_source(url):
    host = source_domain(url)
    return host in GOV_DOMAINS or any(host.endswith("." + d) for d in GOV_DOMAINS)

def is_government_entity(name, text=""):
    n = str(name or "").lower()
    strong_name = ["tcu", "tce ", "prefeitura", "ministério", "ministerio", "secretaria", "tribunal de contas", "câmara municipal", "camara municipal", "senado", "câmara dos deputados", "camara dos deputados"]
    if any(x in n for x in strong_name):
        return True
    # Só usamos contexto governamental para bloquear quando há sinais explícitos de compra pública.
    gov = term_hits(text, GOV_TERMS)
    return len(gov) >= 2 and not term_hits(text, ["empresa privada", "companhia privada", "grupo empresarial", "corporação"])

def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value)[:19], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None

def freshness(published_at, title="", body=""):
    dt = parse_date(published_at)
    if not dt:
        # Tenta recuperar uma data explícita da própria página/snippet.
        text = str(body or "") + " " + str(title or "")
        patterns = [
            r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b",
            r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/(20\d{2})\b",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if not m:
                continue
            try:
                if pat.startswith(r"\b(20"):
                    dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
                else:
                    dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
                break
            except Exception:
                pass
    if not dt:
        return "UNKNOWN", 999
    days = max(0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    if days <= HOT_DAYS:
        return "HOT", int(days)
    if days <= MAX_DAYS:
        return "WARM", int(days)
    return "STALE", int(days)

def valid_company(name):
    n = norm(name).strip(" -–—|,:;.")
    low = n.lower()
    if not n or len(n) < 3 or len(n) > 120 or low in GENERIC_NAMES:
        return False
    if any(x in low for x in ["google news", "reuters", "exame", "uol", "g1", "globo notícias", "globo noticias"]):
        return False
    if len(n.split()) > 12 or len(re.findall(r"\d", n)) > 8:
        return False
    if is_government_entity(n, n):
        return False
    return True

def clean_company(name):
    n = norm(name)
    n = re.sub(r"^\s*(a|o|as|os|uma|um)\s+", "", n, flags=re.I)
    n = re.sub(r"\s*[-–—|]\s*(reuters|exame|valor|g1|uol|forbes|globo|estadão|estadao)\s*$", "", n, flags=re.I)
    return n.strip(" -–—|,:;.")

# ============================================================
# ENTITY RESOLUTION
# ============================================================

def extract_company_candidates(title, body, url, explicit=""):
    candidates = []
    if explicit and valid_company(explicit):
        candidates.append(("explicit", clean_company(explicit), 100))

    # Manchetes do tipo: Empresa X anuncia / sofre / amplia / enfrenta...
    patterns = [
        r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*){0,7})\s+(?:anuncia|anunciou|inicia|iniciou|amplia|ampliou|expande|expandiu|enfrenta|sofre|sofreu|revela|revelou|adota|adotou|investe|investiu|planeja|busca|procura)",
        r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*){0,7})\s+(?:tem|teve|é|e)\s+",
    ]
    for pat in patterns:
        m = re.search(pat, title or "")
        if m:
            c = clean_company(m.group(1))
            if valid_company(c):
                candidates.append(("title", c, 90))

    # Nome corporativo explícito no corpo: "A Empresa X..." / "Empresa X, ..."
    body_patterns = [
        r"\b([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*){0,6})\s+(?:anunciou|anuncia|informou|confirmou|revelou|sofreu|enfrenta|está|esta|passou|ampliou|expandiu)",
        r"\b(?:a empresa|a companhia|o grupo)\s+([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-]*){0,5})\b",
    ]
    for pat in body_patterns:
        for m in re.finditer(pat, body[:10000] if body else ""):
            c = clean_company(m.group(1))
            if valid_company(c):
                candidates.append(("body", c, 70))
                break

    # Para página corporativa, o domínio pode ajudar SOMENTE como último recurso.
    host = source_domain(url)
    if host and not is_media(url) and not is_government_source(url):
        base = host.split(".")[0].replace("-", " ")
        if valid_company(base) and len(base) >= 4:
            candidates.append(("domain", base.title(), 35))

    # dedupe
    seen = set(); out = []
    for origin, c, q in sorted(candidates, key=lambda x: -x[2]):
        key = re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()
        if key not in seen:
            seen.add(key); out.append((origin, c, q))
    return out[:12]

def resolve_company(title, body, url, existing):
    candidates = extract_company_candidates(title, body, url)
    for origin, c, _ in candidates:
        if is_government_entity(c, title + " " + body):
            continue
        key = re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()
        for e in existing:
            ek = re.sub(r"[^a-z0-9]+", " ", e.lower()).strip()
            if key == ek or (len(key) >= 7 and (key in ek or ek in key)):
                return e, origin
        if origin in ("explicit", "title", "body"):
            return c, origin
    return "", ""

# ============================================================
# BANCO / MIGRAÇÃO
# ============================================================

def db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS companies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        website TEXT DEFAULT '', icp TEXT DEFAULT 'UNKNOWN',
        created_at TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sources(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER, title TEXT, url TEXT UNIQUE, source_type TEXT,
        publisher TEXT, collected_at TEXT, content TEXT, published_at TEXT, query TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER, source_id INTEGER, kind TEXT, evidence TEXT,
        evidence_type TEXT, confidence TEXT, created_at TEXT,
        UNIQUE(source_id,kind,evidence))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS opportunities(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER UNIQUE, trigger_text TEXT, need TEXT, pain TEXT,
        intent TEXT, dm TEXT, timing TEXT, score INTEGER, confidence TEXT,
        classification TEXT, next_action TEXT, reason TEXT, created_at TEXT, updated_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hunts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT,
        sources_found INTEGER DEFAULT 0, signals_found INTEGER DEFAULT 0,
        companies_found INTEGER DEFAULT 0, new_opportunities INTEGER DEFAULT 0,
        updated_opportunities INTEGER DEFAULT 0, unassigned INTEGER DEFAULT 0,
        discarded INTEGER DEFAULT 0)""")
    conn.commit()
    return conn

# ============================================================
# COLETA
# ============================================================

def rss_search(query):
    q = f"{query} when:5d"
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    rows = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        for item in soup.find_all("item"):
            title = clean_text(item.title.get_text(" ", strip=True) if item.title else "")
            link = item.link.get_text(strip=True) if item.link else ""
            desc = clean_text(item.description.get_text(" ", strip=True) if item.description else "")
            pub = item.pubDate.get_text(strip=True) if item.pubDate else ""
            publisher = item.source.get_text(strip=True) if item.source else ""
            if title and link:
                rows.append({"title": title, "url": link, "body": desc, "publisher": publisher,
                             "source_type": "NEWS", "published_at": pub, "query": query})
    except Exception:
        pass
    return rows

def web_search(query, limit=8):
    rows = []
    try:
        url = f"https://www.bing.com/search?q={quote_plus(query)}&count={limit}&setlang=pt-BR"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if not a:
                continue
            href = a.get("href", "")
            title = clean_text(a.get_text(" ", strip=True))
            snippet = clean_text((li.select_one(".b_caption") or li).get_text(" ", strip=True))
            if href.startswith("http") and title and not is_government_source(href):
                rows.append({"title": title, "url": href, "body": snippet, "publisher": source_domain(href),
                             "source_type": "WEB", "published_at": "", "query": query})
    except Exception:
        pass
    return rows

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code >= 400:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return clean_text(soup.get_text(" ", strip=True))[:16000]
    except Exception:
        return ""

# ============================================================
# SIGNAL / QUALIFICATION
# ============================================================

def hiring_only(text):
    return any(has_term(text, x) for x in ["vaga de", "vagas para", "estamos contratando", "processo seletivo", "recrutamento"])

def evidence_snippets(text, terms, limit=2):
    text = clean_text(text)
    spans = []
    for term in terms:
        for m in re.finditer(re.escape(term), text, flags=re.I):
            spans.append(text[max(0, m.start()-180):min(len(text), m.end()+320)].strip())
            if len(spans) >= limit:
                return spans
    return spans

def validate_intent(text, source_type):
    # Intenção de compra exige evidência comercial explícita.
    if hiring_only(text):
        return "NONE"
    if term_hits(text, INTENT_STRONG):
        return "HIGH"
    return "NONE"

def classify_entity(company, evidence):
    if not company:
        return "UNKNOWN"
    if is_government_entity(company, evidence):
        return "GOVERNMENT"
    return "PRIVATE"

def infer_icp(company, evidence):
    # ICP mínimo para este Hunter: empresa privada B2B com ambiente tecnológico
    # relevante. Não fingimos conhecer a quantidade de endpoints quando a fonte não informa.
    entity = classify_entity(company, evidence)
    if entity != "PRIVATE":
        return "CLEARLY_OUT"
    tech = len(set(term_hits(evidence, TECH_TERMS)))
    complexity = len(set(term_hits(evidence, ["infraestrutura", "cloud", "nuvem", "data center", "sistemas", "rede", "endpoints", "servidores", "unidades"])))
    if tech >= 2 and complexity >= 1:
        return "LIKELY"
    return "UNKNOWN"

def classify_company(company, signals, source_rows):
    evidence = " ".join(s["evidence"] for s in signals)
    entity = classify_entity(company, evidence)
    if entity != "PRIVATE":
        return {"icp":"CLEARLY_OUT", "intent":"NONE", "need":"NONE", "pain":"NONE", "trigger":"NONE", "dm":"NONE", "timing":"NONE", "score":0, "confidence":"HIGH", "classification":"IGNORE", "reason":"Entidade pública/não privada."}

    # Só consideramos evidência recente na qualificação.
    recent_sources = []
    for src in source_rows:
        freshness_class, days = freshness(src.get("published_at"), src.get("title",""), src.get("content",""))
        if freshness_class in ("HOT", "WARM"):
            recent_sources.append((src, freshness_class, days))

    if not recent_sources:
        return {"icp":"UNKNOWN", "intent":"NONE", "need":"NONE", "pain":"NONE", "trigger":"NONE", "dm":"NONE", "timing":"STALE", "score":0, "confidence":"HIGH", "classification":"WATCH", "reason":"Sem fonte comprovadamente recente (≤5 dias)."}

    # Intent só conta quando existe fonte direta não-mídia.
    intent_direct = False
    intent_high = False
    for src, _, _ in recent_sources:
        if not is_media(src.get("url","")) and validate_intent(src.get("content",""), src.get("source_type","")) == "HIGH":
            intent_direct = True
            intent_high = True
            break

    need = "HIGH" if len({s["source_id"] for s in signals if s["kind"]=="NEED_SIGNAL" and s["source_id"]}) >= 2 else ("MEDIUM" if any(s["kind"]=="NEED_SIGNAL" for s in signals) else "NONE")
    pain = "HIGH" if len({s["source_id"] for s in signals if s["kind"]=="PAIN_RISK" and s["source_id"]}) >= 2 else ("MEDIUM" if any(s["kind"]=="PAIN_RISK" for s in signals) else "NONE")
    trigger = "MEDIUM" if any(s["kind"]=="BUSINESS_TRIGGER" for s in signals) else "NONE"
    dm = "LIKELY" if any(s["kind"]=="DECISION_MAKER" for s in signals) else "NONE"

    icp = infer_icp(company, evidence)
    intent = "HIGH" if intent_high else "NONE"
    hot = any(x[1] == "HOT" for x in recent_sources)
    timing = "HIGH" if hot else "MEDIUM"

    # Score é consequência dos gates, não o contrário.
    score = 0
    score += 15 if icp == "LIKELY" else 0
    score += 25 if intent == "HIGH" else 0
    score += 20 if need == "HIGH" else (10 if need == "MEDIUM" else 0)
    score += 20 if pain == "HIGH" else (10 if pain == "MEDIUM" else 0)
    score += 10 if timing == "HIGH" else 5
    score += 5 if dm == "LIKELY" else 0
    score = min(score, 100)

    # GATE DEFINITIVO: não existe WARM/HOT sem intenção comercial explícita.
    if icp == "LIKELY" and intent == "HIGH" and need in ("MEDIUM","HIGH") and pain in ("MEDIUM","HIGH"):
        classification = "HOT" if hot and score >= 80 else "WARM"
    elif pain != "NONE" or need != "NONE" or trigger != "NONE":
        classification = "WATCH"
    else:
        classification = "IGNORE"

    confidence = "HIGH" if intent == "HIGH" and need != "NONE" and pain != "NONE" else ("MEDIUM" if any(x != "NONE" for x in [need,pain,trigger]) else "LOW")
    return {"icp":icp,"intent":intent,"need":need,"pain":pain,"trigger":trigger,"dm":dm,"timing":timing,"score":score,"confidence":confidence,"classification":classification,
            "reason":f"Entity={entity} | ICP={icp} | Intent={intent} | Need={need} | Pain={pain} | Timing={timing} | DirectIntent={intent_direct}"}

def classify_signal_type(text):
    return {
        "BUYING_INTENT": term_hits(text, INTENT_STRONG),
        "NEED_SIGNAL": term_hits(text, TECH_TERMS),
        "BUSINESS_TRIGGER": term_hits(text, TRIGGER_TERMS),
        "PAIN_RISK": term_hits(text, PAIN_TERMS),
        "DECISION_MAKER": term_hits(text, DM_TERMS),
    }

# ============================================================
# CAÇA
# ============================================================

def find_or_create_company(conn, name, now):
    name = clean_company(name)
    if not valid_company(name):
        return None
    row = conn.execute("SELECT id FROM companies WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        return row["id"]
    conn.execute("INSERT INTO companies(name,website,icp,created_at,updated_at) VALUES(?,?,?,?,?)", (name,"","UNKNOWN",now,now))
    conn.commit()
    return conn.execute("SELECT id FROM companies WHERE name=?", (name,)).fetchone()["id"]

def save_source(conn, item, company_id, content):
    row = conn.execute("SELECT id FROM sources WHERE url=?", (item["url"],)).fetchone()
    now = datetime.utcnow().isoformat(timespec="seconds")
    if row:
        sid = row["id"]
        conn.execute("UPDATE sources SET company_id=COALESCE(company_id,?),title=?,publisher=?,content=?,published_at=?,query=? WHERE id=?", (company_id,item["title"],item.get("publisher",""),content[:16000],item.get("published_at",""),item.get("query",""),sid))
    else:
        cur = conn.execute("""INSERT INTO sources(company_id,title,url,source_type,publisher,collected_at,content,published_at,query) VALUES(?,?,?,?,?,?,?,?,?)""", (company_id,item["title"],item["url"],item.get("source_type","NEWS"),item.get("publisher",""),now,content[:16000],item.get("published_at",""),item.get("query","")))
        sid = cur.lastrowid
    conn.commit()
    return sid

def save_signals(conn, company_id, source_id, evidence_text):
    generated = []
    intent = validate_intent(evidence_text, "")
    # Intent só nasce de fonte direta; caller já garante isso.
    if intent == "HIGH":
        for ev in evidence_snippets(evidence_text, INTENT_STRONG, 2):
            generated.append(("BUYING_INTENT", ev, "HIGH"))
    for kind, terms in [("NEED_SIGNAL",TECH_TERMS),("BUSINESS_TRIGGER",TRIGGER_TERMS),("PAIN_RISK",PAIN_TERMS),("DECISION_MAKER",DM_TERMS)]:
        for ev in evidence_snippets(evidence_text, terms, 2):
            generated.append((kind, ev, "MEDIUM"))
    count = 0
    for kind, ev, conf in generated:
        conn.execute("INSERT OR IGNORE INTO signals(company_id,source_id,kind,evidence,evidence_type,confidence,created_at) VALUES(?,?,?,?,?,?,?)", (company_id,source_id,kind,ev,"FACT",conf,datetime.utcnow().isoformat(timespec="seconds")))
        if conn.execute("SELECT changes()").fetchone()[0]: count += 1
    conn.commit()
    return count

def requalify_all(conn):
    stats = {"hot":0,"warm":0,"watch":0,"ignore":0}
    companies = conn.execute("SELECT * FROM companies").fetchall()
    for c in companies:
        src_rows = [dict(r) for r in conn.execute("SELECT * FROM sources WHERE company_id=?", (c["id"],)).fetchall()]
        sig_rows = [dict(r) for r in conn.execute("SELECT * FROM signals WHERE company_id=?", (c["id"],)).fetchall()]
        if not sig_rows:
            continue
        result = classify_company(c["name"], sig_rows, src_rows)
        now = datetime.utcnow().isoformat(timespec="seconds")
        reason = result["reason"]
        next_action = {"HOT":"Abordar imediatamente e validar dor/decisor.","WARM":"Abordar consultivamente e validar projeto.","WATCH":"Monitorar e buscar evidência comercial.","IGNORE":"Sem ação comercial."}[result["classification"]]
        vals = (next((s["evidence"] for s in sig_rows if s["kind"]=="BUSINESS_TRIGGER"),""), next((s["evidence"] for s in sig_rows if s["kind"]=="NEED_SIGNAL"),""), next((s["evidence"] for s in sig_rows if s["kind"]=="PAIN_RISK"),""), result["intent"], next((s["evidence"] for s in sig_rows if s["kind"]=="DECISION_MAKER"),""), result["timing"], result["score"], result["confidence"], result["classification"], next_action, reason, now, c["id"])
        exists = conn.execute("SELECT id FROM opportunities WHERE company_id=?", (c["id"],)).fetchone()
        if exists:
            conn.execute("UPDATE opportunities SET trigger_text=?,need=?,pain=?,intent=?,dm=?,timing=?,score=?,confidence=?,classification=?,next_action=?,reason=?,updated_at=? WHERE company_id=?", vals)
        else:
            conn.execute("INSERT INTO opportunities(company_id,trigger_text,need,pain,intent,dm,timing,score,confidence,classification,next_action,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (c["id"],)+vals[:-1]+(now,))
        conn.execute("UPDATE companies SET icp=?,updated_at=? WHERE id=?", (result["icp"],now,c["id"]))
        stats[result["classification"].lower()] = stats.get(result["classification"].lower(),0)+1
    conn.commit()
    return stats

def run_hunt():
    conn = db(); started = datetime.utcnow().isoformat(timespec="seconds")
    collected=[]; seen=set(); diag={"rss":0,"web":0,"stale":0,"gov":0,"media":0,"companies":0,"signals":0,"intent":0}
    progress=st.progress(0,text="MILO: procurando fontes quentes (0–5 dias)...")

    # RSS: ampla descoberta recente.
    for i,q in enumerate(SEARCH_QUERIES):
        for item in rss_search(q):
            if item["url"] not in seen:
                seen.add(item["url"]); collected.append(item); diag["rss"]+=1
        progress.progress(int((i+1)/len(SEARCH_QUERIES)*55), text=f"MILO RSS {i+1}/{len(SEARCH_QUERIES)}")

    # WEB: só as consultas mais comerciais; recência via Bing after:.
    cutoff=(datetime.now(timezone.utc)-timedelta(days=MAX_DAYS)).date().isoformat()
    web_queries=SEARCH_QUERIES[:18]
    for j,q in enumerate(web_queries):
        q2=f"{q} after:{cutoff}"
        for item in web_search(q2,8):
            if item["url"] not in seen:
                seen.add(item["url"]); collected.append(item); diag["web"]+=1
        progress.progress(55+int((j+1)/len(web_queries)*25), text=f"MILO WEB {j+1}/{len(web_queries)}")

    # Primeiro filtro: GOV nunca entra na caça comercial.
    filtered=[]
    for item in collected:
        txt=item["title"]+" "+item.get("body","")
        if is_government_source(item["url"]): diag["gov"]+=1; continue
        if is_government_entity("",txt) and len(term_hits(txt,GOV_TERMS))>=2: diag["gov"]+=1; continue
        fc,_=freshness(item.get("published_at"),item.get("title"),item.get("body"))
        if fc in ("STALE", "UNKNOWN"):
            diag["stale"]+=1; continue
        filtered.append(item)
    collected=filtered

    # Processa somente fontes que têm relação com dor/necessidade/compra.
    candidates=[]
    for item in collected:
        txt=item["title"]+" "+item.get("body","")
        if term_hits(txt, INTENT_STRONG+TECH_TERMS+PAIN_TERMS+TRIGGER_TERMS):
            candidates.append(item)
    candidates=candidates[:300]

    progress.progress(80,text=f"HUNTER: validando {len(candidates)} fontes quentes...")
    conn=db(); existing=[r["name"] for r in conn.execute("SELECT name FROM companies").fetchall()]
    touched=set(); signals_new=0

    for i,item in enumerate(candidates):
        title=clean_text(item["title"]); url=item["url"]; body=clean_text(item.get("body",""))
        # Busca página completa para obter contexto e descobrir entidade.
        page=fetch_page(url) if len(body)<1000 or item.get("source_type")=="WEB" else body
        content=clean_text(f"{title}. {page or body}")
        if is_government_source(url) or is_government_entity("",title+" "+content):
            continue

        name,origin=resolve_company(title,content,url,existing)
        if not name:
            continue
        if is_government_entity(name,title+" "+content):
            continue
        cid=find_or_create_company(conn,name,datetime.utcnow().isoformat(timespec="seconds"))
        if not cid: continue
        if name not in existing: existing.append(name)
        touched.add(cid)
        sid=save_source(conn,item,cid,content)

        # Fonte direta pode gerar intent. Notícia não pode.
        direct=not is_media(url)
        if direct:
            n=save_signals(conn,cid,sid,content); signals_new+=n; diag["signals"]+=n
            if validate_intent(content,item.get("source_type",""))=="HIGH": diag["intent"]+=1
        else:
            # Notícia: somente dor/trigger/need como evidência de contexto.
            generated=[]
            for kind,terms in [("NEED_SIGNAL",TECH_TERMS),("BUSINESS_TRIGGER",TRIGGER_TERMS),("PAIN_RISK",PAIN_TERMS)]:
                for ev in evidence_snippets(content,terms,2): generated.append((kind,ev,"MEDIUM"))
            for kind,ev,conf in generated:
                conn.execute("INSERT OR IGNORE INTO signals(company_id,source_id,kind,evidence,evidence_type,confidence,created_at) VALUES(?,?,?,?,?,?,?)",(cid,sid,kind,ev,"FACT",conf,datetime.utcnow().isoformat(timespec="seconds")))
                if conn.execute("SELECT changes()").fetchone()[0]: signals_new+=1; diag["signals"]+=1
            conn.commit()

        if i%10==0: progress.progress(80+int((i+1)/max(1,len(candidates))*20),text=f"HUNTER: {i+1}/{len(candidates)}")

    progress.empty()
    stats=requalify_all(conn)
    finished=datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("INSERT INTO hunts(started_at,finished_at,sources_found,signals_found,companies_found,new_opportunities,updated_opportunities,unassigned,discarded) VALUES(?,?,?,?,?,?,?,?,?)",(started,finished,len(collected),signals_new,len(touched),stats.get("hot",0)+stats.get("warm",0),0,0,diag["gov"]+diag["stale"]))
    conn.commit()
    return diag,len(collected),signals_new,len(touched),stats

# ============================================================
# UI
# ============================================================
conn=db()
companies_count=conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"]
signals_count=conn.execute("SELECT COUNT(*) c FROM signals").fetchone()["c"]
hot_count=conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification='HOT'").fetchone()["c"]
warm_count=conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification='WARM'").fetchone()["c"]
watch_count=conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification='WATCH'").fetchone()["c"]

st.title("🔎 HUNTER TECHS")
st.caption("V12 • HOT SOURCE HUNTER — empresas privadas • 0–3 dias prioritário • até 5 dias • dor TECHS + evidência comercial")
cols=st.columns(5)
cols[0].metric("Empresas",companies_count)
cols[1].metric("Sinais",signals_count)
cols[2].metric("Oportunidades",hot_count+warm_count)
cols[3].metric("HOT",hot_count)
cols[4].metric("WARM",warm_count)
st.caption(f"WATCH: {watch_count} • WATCH não é oportunidade • GOV/licitação não participa da caça")

if st.button("🚀 IR PARA CAÇA REAL",type="primary",use_container_width=True):
    with st.spinner("Caçando empresas privadas com dor recente..."):
        diag,sources,sigs,comps,stats=run_hunt()
    st.success(f"Caça concluída — {sources} fontes recentes | {sigs} sinais novos | {comps} empresas | HOT {stats.get('hot',0)} | WARM {stats.get('warm',0)} | WATCH {stats.get('watch',0)}")
    st.write("**Diagnóstico da caça**")
    st.dataframe(pd.DataFrame([diag]),use_container_width=True,hide_index=True)

# TESTE DE REGRESSÃO — o caso que derrubou versões anteriores.
st.subheader("🧪 Teste de integridade comercial")
test = {
    "TCU + contratação de nuvem do governo": "IGNORE",
    "Licitação / pregão / edital": "IGNORE",
    "Notícia de ransomware sem compra": "WATCH",
    "Trigger sem intenção": "WATCH",
    "Intent comercial + necessidade + dor + empresa privada": "WARM/HOT",
}
st.dataframe(pd.DataFrame([{"Cenário":k,"Resultado esperado":v} for k,v in test.items()]),use_container_width=True,hide_index=True)

# OPORTUNIDADES — somente HOT/WARM.
tab1,tab2,tab3,tab4=st.tabs(["🎯 Oportunidades","🔥 Fontes quentes","🏢 Empresas","📊 Histórico"])
with tab1:
    rows=conn.execute("""SELECT o.*,c.name company,c.icp,
        (SELECT src.title FROM sources src JOIN signals ss ON ss.source_id=src.id WHERE ss.company_id=o.company_id ORDER BY src.id DESC LIMIT 1) source_title,
        (SELECT src.url FROM sources src JOIN signals ss ON ss.source_id=src.id WHERE ss.company_id=o.company_id ORDER BY src.id DESC LIMIT 1) source_url
        FROM opportunities o JOIN companies c ON c.id=o.company_id WHERE o.classification IN ('HOT','WARM') ORDER BY CASE o.classification WHEN 'HOT' THEN 1 ELSE 2 END,o.score DESC,o.updated_at DESC""").fetchall()
    if rows:
        df=pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df,use_container_width=True,hide_index=True)
    else: st.info("Nenhuma oportunidade real qualificada. Isso é preferível a falso positivo.")
with tab2:
    rows=conn.execute("""SELECT s.id,c.name company,s.kind,s.confidence,s.evidence,src.title,src.url,src.publisher,src.source_type,src.published_at,src.collected_at FROM signals s LEFT JOIN companies c ON c.id=s.company_id LEFT JOIN sources src ON src.id=s.source_id ORDER BY s.id DESC LIMIT 1000""").fetchall()
    if rows:
        df=pd.DataFrame([dict(r) for r in rows]); st.dataframe(df,use_container_width=True,hide_index=True)
        st.download_button("⬇️ Exportar sinais CSV",df.to_csv(index=False).encode("utf-8-sig"),"hunter_techs_sinais.csv","text/csv")
    else: st.info("Nenhuma fonte quente registrada.")
with tab3:
    rows=conn.execute("SELECT id,name,website,icp,created_at,updated_at FROM companies ORDER BY name").fetchall()
    if rows: st.dataframe(pd.DataFrame([dict(r) for r in rows]),use_container_width=True,hide_index=True)
    else: st.info("Nenhuma empresa.")
with tab4:
    rows=conn.execute("SELECT * FROM hunts ORDER BY id DESC LIMIT 20").fetchall()
    if rows: st.dataframe(pd.DataFrame([dict(r) for r in rows]),use_container_width=True,hide_index=True)
    else: st.info("Nenhuma caça registrada.")

st.divider()
st.caption("V12: GOV/PNCP/licitação fora da caça. Fonte NEWS é descoberta/dor; intent comercial exige fonte direta. Oportunidade = empresa privada + ICP provável + necessidade + dor + intenção de compra + recência.")
