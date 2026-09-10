
import io
import re
import sqlite3
import hashlib
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="HUNTER TECHS", page_icon="🔎", layout="wide")

DB = "hunter.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}

# ============================================================
# CONFIGURAÇÃO
# ============================================================

SEARCH_QUERIES = [
    # COMPRA / PROJETO REAL — linguagem empresarial, sem governo/licitação
    '"RFP" "segurança da informação" empresa',
    '"RFQ" tecnologia empresa',
    '"request for proposal" cybersecurity company',
    '"request for quotation" IT company',
    '"busca de fornecedor" tecnologia empresa',
    '"seleção de fornecedor" tecnologia empresa',
    '"buscando fornecedor" TI empresa',
    '"buscando parceiro" "segurança" empresa',
    '"parceiro de tecnologia" "segurança" empresa',
    '"serviços gerenciados" "empresa" TI',
    '"MSSP" empresa segurança',
    '"SOC" empresa "fornecedor"',
    '"EDR" empresa "fornecedor"',
    '"backup" empresa "fornecedor"',
    '"firewall" empresa "fornecedor"',
    '"SASE" empresa "fornecedor"',
    # DOR OPERACIONAL REAL
    'empresa ransomware "infraestrutura"',
    'empresa "incidente de segurança" "TI"',
    'empresa "indisponibilidade" "sistemas"',
    'empresa "falha de infraestrutura" TI',
    'empresa "perda de dados" tecnologia',
    'empresa "vulnerabilidade" "infraestrutura"',
    'empresa "sobrecarga da equipe de TI"',
    'empresa "falta de equipe" TI segurança',
    'empresa "monitoramento 24x7" TI',
    'empresa "continuidade de negócios" TI',
    'empresa "disaster recovery" TI',
    # TRIGGERS QUE GERAM DEMANDA DE INFRA/SEGURANÇA
    '"novo CIO" empresa infraestrutura',
    '"novo CTO" empresa infraestrutura',
    '"novo diretor de TI" empresa',
    '"novo gerente de TI" empresa',
    'empresa "migração para cloud"',
    'empresa "migração para nuvem" infraestrutura',
    'empresa "modernização da infraestrutura"',
    'empresa "expansão" "infraestrutura de TI"',
    'empresa "novas unidades" infraestrutura TI',
    'empresa "data center" expansão',
    'empresa aquisição "infraestrutura de TI"',
    'empresa fusão "infraestrutura de TI"',
]

INTENT_STRONG = [
    "rfp", "rfq", "request for proposal", "request for quotation",
    "solicitação de proposta", "solicitacao de proposta",
    "pedido de cotação", "pedido de cotacao",
    "busca de fornecedor", "procura fornecedor",
    "procura por fornecedor", "supplier search",
    "tender", "procurement", "vendor selection", "vendor change",
    "seleção de fornecedor", "selecao de fornecedor",
    "cotação de fornecedor", "cotacao de fornecedor",
    "licitação", "licitacao", "edital", "pregão", "pregao",
    "contratação de serviços", "contratacao de servicos",
]
INTENT_CONTEXT = ["cotação", "cotacao", "orçamento", "orcamento", "comprar", "aquisição", "aquisicao", "contratar", "contratação", "contratacao"]
TECH_TERMS = [
    "rmm", "edr", "xdr", "backup", "monitoramento", "monitorização",
    "endpoint", "endpoints", "firewall", "sase", "soc", "mssp",
    "segurança da informação", "seguranca da informacao", "cibersegurança",
    "ciberseguranca", "cybersecurity", "infraestrutura", "infraestrutura de ti",
    "serviços gerenciados", "servicos gerenciados", "cloud", "nuvem",
    "disaster recovery", "continuidade", "governança", "governanca",
    "gestão de ti", "gestao de ti", "ti",
]
TRIGGER_TERMS = [
    "novo cio", "novo cto", "novo diretor de ti", "novo gerente de ti",
    "expansão", "expansao", "aquisição", "aquisicao", "fusão", "fusao",
    "transformação digital", "transformacao digital", "migração para nuvem",
    "migracao para nuvem", "modernização", "modernizacao",
    "novas unidades", "novas lojas", "abertura de lojas", "data center",
    "erp", "incidente de segurança", "incidente de seguranca",
]
PAIN_TERMS = [
    "downtime", "indisponibilidade", "falha", "falhas", "ataque", "ransomware",
    "vulnerabilidade", "risco", "interrupção", "interrupcao", "perda de dados",
    "data loss", "incidente", "sobrecarga", "equipe reduzida", "falta de equipe",
]
DM_TERMS = [
    "cio", "cto", "diretor de ti", "diretor de tecnologia", "gerente de ti",
    "gerente de tecnologia", "head de tecnologia", "head of technology",
    "diretor de segurança", "diretor de infraestrutura", "ciso", "it manager",
]

MEDIA_NAMES = {
    "google news", "g1", "globo", "uol", "exame", "valor", "estadao",
    "estadão", "folha", "terra", "cnn", "forbes", "reuters", "bloomberg",
    "infomoney", "canaltech", "tecmundo", "olhar digital", "computerworld",
    "it forum", "ti inside", "startse", "convergencia digital",
}
MEDIA_DOMAINS = {
    "news.google.com", "google.com", "g1.globo.com", "oglobo.globo.com",
    "exame.com", "valor.globo.com", "estadao.com.br", "folha.uol.com.br",
    "uol.com.br", "terra.com.br", "cnnbrasil.com.br", "forbes.com",
    "reuters.com", "bloomberg.com", "infomoney.com.br", "canaltech.com.br",
    "tecmundo.com.br", "olhardigital.com.br", "itforum.com.br",
}

# Fontes que nunca podem virar evidência comercial final.
EXCLUDED_DOMAINS = {
    "pncp.gov.br", "compras.gov.br", "gov.br", "bcb.gov.br",
    "tcu.gov.br", "tce.sp.gov.br", "tce.rj.gov.br",
    "jus.br", "leg.br", "camara.leg.br", "senado.leg.br",
}

EXCLUDED_SOURCE_TERMS = [
    "licitação", "licitacao", "edital", "pregão", "pregao",
    "dispensa de licitação", "dispensa de licitacao", "pregão eletrônico",
    "pregao eletronico", "processo licitatório", "processo licitatorio",
    "compras públicas", "compras publicas", "órgão público", "orgao publico",
    "prefeitura", "município", "municipio", "secretaria de", "estado do",
]

B2B_DIRECT_TERMS = [
    "fornecedor", "fornecedores", "parceiro", "parceiros", "rfp", "rfq",
    "request for proposal", "request for quotation", "mssP", "soc", "edr",
    "rmm", "sase", "backup", "firewall", "serviços gerenciados",
    "servicos gerenciados", "monitoramento 24x7", "disaster recovery",
]

GENERIC_NAMES = {
    "empresa", "companhia", "organização", "organizacao", "grupo", "cliente",
    "fornecedor", "governo", "prefeitura", "estado", "município", "municipio",
    "brasil", "mercado", "setor", "indústria", "industria", "banco",
}

# ============================================================
# DIAGNÓSTICO
# ============================================================

def empty_diag():
    return {
        "sources": 0,
        "candidate_extracted": 0,
        "candidate_rejected": 0,
        "resolved_existing": 0,
        "resolved_new": 0,
        "not_resolved": 0,
        "signals_total": 0,
        "signals_with_company": 0,
        "signals_without_company": 0,
        "reject_invalid": 0,
        "reject_media": 0,
        "reject_generic": 0,
        "reject_short": 0,
        "reject_long": 0,
        "domain_candidate": 0,
        "title_candidate": 0,
        "body_candidate": 0,
        "explicit_candidate": 0,
        "examples": [],
        "reprocessed": 0,
        "reprocessed_resolved": 0,
    }

def diag_example(diag, title, candidate, reason, source_type="", url=""):
    if len(diag["examples"]) < 20:
        diag["examples"].append({
            "Título": title[:180],
            "Candidato": candidate or "",
            "Motivo": reason,
            "Tipo": source_type,
            "URL": url[:180],
        })

# ============================================================
# TEXTO / MATCH
# ============================================================

def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def clean_text(s):
    return norm(BeautifulSoup(str(s or ""), "html.parser").get_text(" ", strip=True))

def term_pattern(term):
    t = re.escape(term.lower().strip())
    # Acrônimos/termos curtos precisam de fronteira de palavra.
    if len(term.strip()) <= 3:
        return rf"(?<!\w){t}(?!\w)"
    return t

def has_term(text, term):
    return bool(re.search(term_pattern(term), str(text or "").lower()))

def term_hits(text, terms):
    return [t for t in terms if has_term(text, t)]

def source_domain(url):
    try:
        host = (urlparse(url).netloc or "").lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""

def valid_company(name):
    n = norm(name).strip(" -–—|,:;.")
    low = n.lower()
    if not n or len(n) < 3 or len(n) > 120:
        return False
    if low in GENERIC_NAMES or low in MEDIA_NAMES:
        return False
    if any(x in low for x in ["google news", "reuters", "uol", "exame", "globo notícias", "globo noticias"]):
        return False
    if len(re.findall(r"\d", n)) > 8:
        return False
    if len(n.split()) > 14:
        return False
    return True

def clean_company(name):
    if not name:
        return ""
    n = norm(name)
    n = re.sub(r"^\s*(a|o|as|os|uma|um)\s+", "", n, flags=re.I)
    n = re.sub(r"\s*[-–—|]\s*(reuters|exame|valor|g1|uol|forbes|globo|estadão|estadao)\s*$", "", n, flags=re.I)
    n = re.sub(r"^(empresa|companhia|grupo)\s+", "", n, flags=re.I)
    return n.strip(" -–—|,:;.")

def validate_company_name(name):
    return valid_company(clean_company(name))

# ============================================================
# ENTITY RESOLVER COM RASTREABILIDADE
# ============================================================

def strip_publisher_suffix(title, publisher=""):
    """Remove suffixes comuns de manchetes do Google News."""
    t = clean_text(title)
    if publisher:
        t = re.sub(rf"\s+[|–—-]\s*{re.escape(clean_text(publisher))}\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+[|–—-]\s*(g1|uol|exame|valor|reuters|forbes|cnn brasil|terra|estadao|estadão)\s*$", "", t, flags=re.I)
    return t.strip(" -–—|")

LEGAL_SUFFIX_RE = re.compile(
    r"\b(?:S\.?A\.?|S/A|Ltda\.?|Limitada|EIRELI|S\.A\.S\.?|Corp\.?|Corporation|Inc\.?|LLC|PLC|Holding|Participações|Participacoes)\b",
    flags=re.I,
)

# Palavras que frequentemente aparecem como parte da manchete, mas não são empresa.
ENTITY_STOPWORDS = {
    "novo", "nova", "novos", "novas", "empresa", "companhia", "grupo", "mercado",
    "setor", "indústria", "industria", "banco", "bancos", "rede", "redes", "varejo",
    "tecnologia", "infraestrutura", "segurança", "seguranca", "cibersegurança",
    "ciberseguranca", "cloud", "nuvem", "dados", "sistemas", "serviços", "servicos",
    "contratação", "contratacao", "projeto", "projetos", "operação", "operacao",
    "diretor", "diretora", "gerente", "gerentes", "cio", "cto", "ciso", "ti",
    "fornecedor", "fornecedores", "cliente", "clientes", "especialista", "especialistas",
    "anuncia", "anunciou", "inicia", "iniciou", "amplia", "ampliou", "expande", "expandiu",
    "contrata", "contratou", "investe", "investiu", "adota", "adotou", "implementa",
    "implementou", "migra", "migrou", "moderniza", "modernizou", "abre", "abriu", "lança", "lançou",
    "busca", "procura", "planeja", "pretende", "vai", "é", "e", "para", "com", "sobre", "contra",
}

GENERIC_ENTITY_PHRASES = {
    "sua empresa", "a empresa", "uma empresa", "companhia", "o grupo", "a companhia",
    "mercado brasileiro", "mercado nacional", "setor de tecnologia", "setor financeiro",
}

def _candidate_quality(name):
    """Pontua uma entidade textual; não é score comercial."""
    c = clean_company(name)
    if not c or not validate_company_name(c):
        return -1
    low = c.lower()
    if low in GENERIC_ENTITY_PHRASES or low in GENERIC_NAMES or low in MEDIA_NAMES:
        return -1
    words = c.split()
    score = 0
    if LEGAL_SUFFIX_RE.search(c):
        score += 80
    if len(words) == 1:
        score += 10
    elif 2 <= len(words) <= 6:
        score += 25
    else:
        score += 5
    if any(w.lower() in ENTITY_STOPWORDS for w in words):
        score -= 20
    if re.search(r"\b(?:Ltda|S\.A\.?|S/A|Corp|Inc|Holding)\b", c, re.I):
        score += 15
    return score

def _add_candidate(candidates, origin, value, strength=0):
    c = clean_company(value)
    if not c or not validate_company_name(c):
        return
    q = _candidate_quality(c) + strength
    if q >= 0:
        candidates.append((origin, c, q))

def extract_company_candidates(title, body, publisher, url, explicit_candidate=""):
    """Resolve entidades com prioridade: PNCP > entidade legal > sujeito da manchete > corpo.

    Importante: regexes de nomes próprios NÃO usam re.I. Isso preserva a capitalização
    original da manchete e reduz a captura de frases inteiras como se fossem empresas.
    """
    candidates = []
    title_clean = strip_publisher_suffix(title, publisher)
    body_clean = clean_text(body)[:10000]

    if explicit_candidate:
        _add_candidate(candidates, "explicit", explicit_candidate, 200)

    # 1) Razão social / marca com sufixo jurídico.
    legal_patterns = [
        r"([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]+){0,7}\s+(?:S\.?A\.?|S/A|Ltda\.?|Limitada|EIRELI|Corp\.?|Corporation|Inc\.?|LLC|Holding))",
        r"((?:[A-Z0-9À-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*\s+){1,6}(?:S\.?A\.?|S/A|Ltda\.?|Limitada|EIRELI|Corp\.?|Corporation|Inc\.?|LLC|Holding))",
    ]
    for pat in legal_patterns:
        for txt, origin in [(title_clean, "title"), (body_clean[:5000], "body")]:
            for m in re.finditer(pat, txt or ""):
                _add_candidate(candidates, origin, m.group(1), 100)

    # 2) Nome entre aspas: comum em notícias sobre uma empresa específica.
    for txt, origin in [(title_clean, "title"), (body_clean[:5000], "body")]:
        for m in re.finditer(r'["“”\']([^"“”\']{3,100})["“”\']', txt or ""):
            value = m.group(1)
            # Só aceita se parecer entidade, não frase verbal.
            if len(value.split()) <= 8 and not any(has_term(value, x) for x in INTENT_STRONG):
                _add_candidate(candidates, origin, value, 65)

    # 3) Sujeito explícito no começo da manchete: "Empresa X anuncia..."
    verbs = r"anuncia|anunciou|inicia|iniciou|amplia|ampliou|expande|expandiu|contrata|contratou|investe|investiu|adota|adotou|implementa|implementou|migra|migrou|moderniza|modernizou|abre|abriu|lança|lancou|lançou|busca|procura|planeja|pretende"
    subject_patterns = [
        rf"^([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*){{0,5}})\s+(?:{verbs})\b",
        rf"^([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*){{0,4}})\s*[:,-]\s+(?:{verbs})\b",
    ]
    for pat in subject_patterns:
        m = re.search(pat, title_clean or "")
        if m:
            _add_candidate(candidates, "title", m.group(1), 75)

    # 4) Padrões linguísticos: "na Empresa", "da Empresa", "Empresa busca...".
    prep_patterns = [
        r"\b(?:na|no|em|da|do|das|dos|pela|pelo|para a|para o|junto à|junto ao)\s+([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*){0,4})",
        rf"\b([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]*){{0,4}})\s+(?:{verbs})\b",
    ]
    for pat in prep_patterns:
        for m in re.finditer(pat, title_clean or ""):
            _add_candidate(candidates, "title", m.group(1), 55)
        for m in re.finditer(pat, body_clean[:5000] or ""):
            _add_candidate(candidates, "body", m.group(1), 35)

    # 5) Sequências de nomes próprios no título — SEM re.I.
    # Permite marcas como "Mercado Livre", "Grupo ABC", etc., mas evita palavras genéricas.
    tokens = re.findall(r"\b[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.'’\-/]{2,}\b", title_clean or "")
    for i in range(len(tokens)):
        for size in range(min(6, len(tokens)-i), 0, -1):
            phrase = " ".join(tokens[i:i+size])
            words = phrase.split()
            if len(words) == 1 and words[0].lower() in ENTITY_STOPWORDS:
                continue
            if any(w.lower() in ENTITY_STOPWORDS for w in words[:-1]):
                continue
            _add_candidate(candidates, "title", phrase, 45 if size >= 2 else 25)

    # 6) Domínio: apenas diagnóstico, nunca empresa gravada automaticamente.
    host = source_domain(url)
    if host and host not in MEDIA_DOMAINS:
        base = host.split(".")[0].replace("-", " ").strip()
        if base and validate_company_name(base):
            _add_candidate(candidates, "domain_candidate", base, 5)

    # Deduplica pelo nome e mantém a evidência mais forte.
    best = {}
    priority = {"explicit": 0, "title": 1, "body": 2, "domain_candidate": 3}
    for origin, c, q in candidates:
        key = re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()
        if key not in best or (q, -priority.get(origin, 9)) > (best[key][2], -priority.get(best[key][0], 9)):
            best[key] = (origin, c, q)

    result = sorted(best.values(), key=lambda x: (-x[2], priority.get(x[0], 9), len(x[1])))
    return [(origin, c) for origin, c, _ in result[:12]]

def resolve_company(title, body, publisher, url, explicit_candidate, existing_names, diag):
    candidates = extract_company_candidates(title, body, publisher, url, explicit_candidate)

    if candidates:
        diag["candidate_extracted"] += 1

    for origin, candidate in candidates:
        if origin == "explicit":
            diag["explicit_candidate"] += 1
        elif origin == "title":
            diag["title_candidate"] += 1
        elif origin == "body":
            diag["body_candidate"] += 1
        elif origin == "domain_candidate":
            diag["domain_candidate"] += 1

        c = clean_company(candidate)
        if not validate_company_name(c):
            diag["candidate_rejected"] += 1
            diag["reject_invalid"] += 1
            continue

        cl = re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()
        for existing in existing_names:
            el = re.sub(r"[^a-z0-9]+", " ", existing.lower()).strip()
            if cl == el or (len(cl) >= 6 and (cl in el or el in cl)):
                diag["resolved_existing"] += 1
                return existing, origin, "EXISTING_MATCH"

        # Domínio é diagnóstico apenas. Não cria empresa sem evidência textual.
        if origin in ("explicit", "title", "body"):
            diag["resolved_new"] += 1
            return c, origin, "NEW_ENTITY"

    diag["not_resolved"] += 1
    if not candidates:
        diag_example(diag, title, "", "ENTITY_NOT_FOUND", "news", url)
    else:
        diag_example(diag, title, candidates[0][1], "CANDIDATE_NOT_CONFIRMED", "news", url)
    return "", "", "NOT_RESOLVED"

def is_excluded_source(url, text=""):
    host = source_domain(url)
    if any(host == d or host.endswith("." + d) for d in EXCLUDED_DOMAINS):
        return True
    low = str(text or "").lower()
    return any(has_term(low, x) for x in EXCLUDED_SOURCE_TERMS)

def is_media_source(url):
    host = source_domain(url)
    return host in MEDIA_DOMAINS or any(host.endswith("." + d) for d in MEDIA_DOMAINS)

def is_direct_b2b_source(url, title="", body=""):
    if is_excluded_source(url, title + " " + body):
        return False
    if is_media_source(url):
        return False
    # Domínio próprio / institucional: é elegível como evidência final.
    return bool(source_domain(url))

# ============================================================
# SIGNAL VALIDATOR
# ============================================================

def has_negative_keywords(text):
    low = str(text or "").lower()
    negatives = [
        "vaga de", "vagas para", "estamos contratando", "oportunidade de emprego",
        "processo seletivo", "recrutamento", "salário", "salario", "carreira",
        "curso de", "evento de", "webinar",
    ]
    return any(has_term(low, x) for x in negatives)

def is_hiring_signal(text):
    low = str(text or "").lower()
    return any(has_term(low, x) for x in [
        "vaga de", "vagas para", "estamos contratando", "contrata profissional",
        "processo seletivo", "recrutamento",
    ])

def validate_buying_intent(evidence, source_type="NEWS", direct_source=False):
    # Buying Intent só existe quando há comportamento de compra observável.
    # Notícia, governo, licitação ou simples trigger jamais geram intent.
    if not direct_source or source_type in ("NEWS", "DISCOVERY", "GOV"):
        return "NONE"
    if is_hiring_signal(evidence):
        return "NONE"
    strong = term_hits(evidence, INTENT_STRONG)
    if strong:
        return "HIGH"
    context = term_hits(evidence, INTENT_CONTEXT)
    technical = term_hits(evidence, TECH_TERMS)
    if context and technical:
        return "MEDIUM"
    return "NONE"

def classify_signal_type(text):
    hits = {
        "BUYING_INTENT": term_hits(text, INTENT_STRONG + INTENT_CONTEXT),
        "NEED_SIGNAL": term_hits(text, TECH_TERMS),
        "BUSINESS_TRIGGER": term_hits(text, TRIGGER_TERMS),
        "PAIN_RISK": term_hits(text, PAIN_TERMS),
        "DECISION_MAKER": term_hits(text, DM_TERMS),
    }
    return hits

def extract_timeline(text):
    low = str(text or "").lower()
    if re.search(r"\b(?:2026|2027)\b", low):
        return "MEDIUM"
    if any(x in low for x in ["imediato", "urgente", "nos próximos dias", "nos proximos dias", "este mês", "este mes"]):
        return "HIGH"
    if any(x in low for x in ["próximos meses", "proximos meses", "planeja", "planeja contratar"]):
        return "MEDIUM"
    return "NONE"

def extract_specificity_signals(text):
    low = str(text or "").lower()
    concrete = [
        "rfp", "rfq", "edital", "pregão", "pregao", "cotação", "cotacao",
        "orçamento", "orcamento", "fornecedor", "contratação", "contratacao",
    ]
    return [x for x in concrete if has_term(low, x)]

def calculate_specificity_bonus(text):
    n = len(extract_specificity_signals(text))
    return min(5, n)

def evidence_snippets(text, terms, max_snippets=3):
    text = clean_text(text)
    if not text:
        return []
    spans = []
    for term in terms:
        for m in re.finditer(term_pattern(term), text, flags=re.I):
            start = max(0, m.start() - 180)
            end = min(len(text), m.end() + 280)
            spans.append(text[start:end].strip())
            if len(spans) >= max_snippets:
                return spans
    return spans

def filter_signals(signals):
    out = []
    for s in signals:
        evidence = s.get("evidence", "")
        kind = s.get("kind", "")
        if kind == "BUYING_INTENT" and (is_hiring_signal(evidence) or has_negative_keywords(evidence)):
            continue
        out.append(s)
    return out

# ============================================================
# BANCO
# ============================================================

def db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS companies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        website TEXT DEFAULT '',
        icp TEXT DEFAULT 'UNKNOWN',
        created_at TEXT,
        updated_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sources(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        title TEXT,
        url TEXT UNIQUE,
        source_type TEXT,
        publisher TEXT,
        collected_at TEXT,
        content TEXT,
        published_at TEXT,
        query TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        source_id INTEGER,
        kind TEXT,
        evidence TEXT,
        evidence_type TEXT,
        confidence TEXT,
        created_at TEXT,
        UNIQUE(source_id,kind,evidence)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS opportunities(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER UNIQUE,
        trigger_text TEXT,
        need TEXT,
        pain TEXT,
        intent TEXT,
        dm TEXT,
        timing TEXT,
        score INTEGER,
        confidence TEXT,
        classification TEXT,
        next_action TEXT,
        reason TEXT,
        created_at TEXT,
        updated_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS hunts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        finished_at TEXT,
        sources_found INTEGER DEFAULT 0,
        signals_found INTEGER DEFAULT 0,
        companies_found INTEGER DEFAULT 0,
        new_opportunities INTEGER DEFAULT 0,
        updated_opportunities INTEGER DEFAULT 0,
        unassigned INTEGER DEFAULT 0,
        discarded INTEGER DEFAULT 0
    )""")
    # --------------------------------------------------------
    # MIGRAÇÃO COMPATÍVEL COM O hunter.db EXISTENTE
    # CREATE TABLE IF NOT EXISTS não altera tabelas antigas.
    # As versões anteriores do HUNTER podem ter criado a tabela
    # hunts com menos colunas, causando OperationalError no INSERT.
    # --------------------------------------------------------
    migrations = {
        "companies": {
            "website": "TEXT DEFAULT ''",
            "icp": "TEXT DEFAULT 'UNKNOWN'",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
        "sources": {
            "company_id": "INTEGER",
            "title": "TEXT",
            "url": "TEXT",
            "source_type": "TEXT",
            "publisher": "TEXT",
            "collected_at": "TEXT",
            "content": "TEXT",
            "published_at": "TEXT",
            "query": "TEXT",
        },
        "signals": {
            "company_id": "INTEGER",
            "source_id": "INTEGER",
            "kind": "TEXT",
            "evidence": "TEXT",
            "evidence_type": "TEXT",
            "confidence": "TEXT",
            "created_at": "TEXT",
        },
        "opportunities": {
            "company_id": "INTEGER",
            "trigger_text": "TEXT",
            "need": "TEXT",
            "pain": "TEXT",
            "intent": "TEXT",
            "dm": "TEXT",
            "timing": "TEXT",
            "score": "INTEGER",
            "confidence": "TEXT",
            "classification": "TEXT",
            "next_action": "TEXT",
            "reason": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
        "hunts": {
            "started_at": "TEXT",
            "finished_at": "TEXT",
            "sources_found": "INTEGER DEFAULT 0",
            "signals_found": "INTEGER DEFAULT 0",
            "companies_found": "INTEGER DEFAULT 0",
            "new_opportunities": "INTEGER DEFAULT 0",
            "updated_opportunities": "INTEGER DEFAULT 0",
            "unassigned": "INTEGER DEFAULT 0",
            "discarded": "INTEGER DEFAULT 0",
        },
    }

    for table, columns in migrations.items():
        existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing_cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    conn.commit()
    return conn

# ============================================================
# COLETA
# ============================================================

def web_search(query, limit=10):
    """Busca web aberta sem API paga. O resultado serve para descobrir páginas;
    a evidência comercial só é aceita depois que a página final é acessada e validada.
    """
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
            if href.startswith("http") and title:
                rows.append({
                    "title": title, "url": href, "body": snippet,
                    "publisher": source_domain(href), "source_type": "WEB",
                    "published_at": "", "query": query,
                })
    except Exception:
        pass
    return rows


def rss_search(query):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        rows = []
        for item in soup.find_all("item"):
            title = clean_text(item.title.get_text(" ", strip=True) if item.title else "")
            link = item.link.get_text(strip=True) if item.link else ""
            desc = clean_text(item.description.get_text(" ", strip=True) if item.description else "")
            pub = item.pubDate.get_text(strip=True) if item.pubDate else ""
            publisher = item.source.get_text(strip=True) if item.source else ""
            if title and link:
                rows.append({
                    "title": title, "url": link, "body": desc,
                    "publisher": publisher, "source_type": "NEWS",
                    "published_at": pub, "query": query,
                })
        return rows
    except Exception:
        return []

def pncp_search():
    rows = []
    base = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
    now = datetime.utcnow()
    final = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    for page in range(1, 7):
        try:
            params = {"dataFinal": final, "pagina": page, "tamanhoPagina": 100}
            r = requests.get(base, params=params, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("data", [])
            if not items:
                break
            for x in items:
                org = x.get("orgaoEntidade", {}) or {}
                company = org.get("razaoSocial") or org.get("nome") or ""
                obj = x.get("objetoCompra") or x.get("objeto") or ""
                link = x.get("linkSistemaOrigem") or x.get("numeroControlePNCP") or ""
                if not link:
                    link = "https://pncp.gov.br/app/editais"
                rows.append({
                    "title": clean_text(obj)[:250] or "Contratação pública",
                    "url": link,
                    "body": clean_text(obj),
                    "publisher": "PNCP",
                    "source_type": "PNCP",
                    "published_at": "",
                    "query": "PNCP propostas abertas",
                    "company_candidate": clean_company(company),
                })
        except Exception:
            break
    return rows

def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code >= 400:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return clean_text(soup.get_text(" ", strip=True))[:12000]
    except Exception:
        return ""

# ============================================================
# EMPRESAS / ICP
# ============================================================

def find_or_create_company(conn, name, now, diag=None):
    name = clean_company(name)
    if not validate_company_name(name):
        if diag is not None:
            diag["candidate_rejected"] += 1
            diag["reject_invalid"] += 1
        return None

    row = conn.execute("SELECT id,name FROM companies WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        return row["id"]

    conn.execute(
        "INSERT INTO companies(name,website,icp,created_at,updated_at) VALUES(?,?,?,?,?)",
        (name, "", "UNKNOWN", now, now),
    )
    conn.commit()
    return conn.execute("SELECT id FROM companies WHERE name=?", (name,)).fetchone()["id"]

def infer_icp(company_name, signals):
    text = " ".join(s["evidence"] for s in signals).lower()
    # Não marcar ICP OUT apenas por uma palavra. A regra precisa de evidência.
    out_terms = ["escola", "universidade", "igreja", "hospital público", "prefeitura"]
    if any(has_term(text, x) for x in out_terms):
        return "UNKNOWN"

    tech = len(term_hits(text, TECH_TERMS))
    intent = len(term_hits(text, INTENT_STRONG))
    if tech >= 2 and intent >= 1:
        return "LIKELY"
    if tech >= 3:
        return "LIKELY"
    return "UNKNOWN"

def independent_counts(signals):
    by = {}
    for kind in ["BUYING_INTENT", "NEED_SIGNAL", "PAIN_RISK", "BUSINESS_TRIGGER", "DECISION_MAKER"]:
        subset = [s for s in signals if s["kind"] == kind]
        sources = {s["source_id"] for s in subset if s["source_id"] is not None}
        by[kind] = {"rows": len(subset), "sources": len(sources), "items": subset}
    return by

def classify_company(company_name, signals):
    by = independent_counts(signals)
    all_text = " ".join(s["evidence"] for s in signals)

    intent_sources = by["BUYING_INTENT"]["sources"]
    need_sources = by["NEED_SIGNAL"]["sources"]
    pain_sources = by["PAIN_RISK"]["sources"]
    trigger_sources = by["BUSINESS_TRIGGER"]["sources"]
    dm_sources = by["DECISION_MAKER"]["sources"]

    # Intent: exige evidência independente. PNCP já chega como HIGH.
    if any(s["confidence"] == "HIGH" and s["kind"] == "BUYING_INTENT" for s in signals):
        intent = "HIGH"
    elif intent_sources >= 2:
        intent = "HIGH"
    elif intent_sources == 1:
        intent = "MEDIUM"
    else:
        intent = "NONE"

    if need_sources >= 2:
        need = "HIGH"
    elif need_sources == 1:
        need = "MEDIUM"
    else:
        need = "NONE"

    if pain_sources >= 2:
        pain = "HIGH"
    elif pain_sources == 1:
        pain = "MEDIUM"
    else:
        pain = "NONE"

    if trigger_sources >= 2:
        trigger = "HIGH"
    elif trigger_sources == 1:
        trigger = "MEDIUM"
    else:
        trigger = "NONE"

    dm = "LIKELY" if dm_sources >= 1 else "NONE"
    timing = extract_timeline(all_text)

    # ICP é gate. UNKNOWN não pode virar HOT.
    icp = infer_icp(company_name, signals)

    score = 0
    score += {"NONE": 0, "UNKNOWN": 7, "LIKELY": 12, "CLEAR": 15}.get(icp, 7)
    score += {"NONE": 0, "MEDIUM": 15, "HIGH": 25, "VERY HIGH": 25}.get(intent, 0)
    score += {"NONE": 0, "MEDIUM": 10, "HIGH": 20}.get(need, 0)
    score += {"NONE": 0, "MEDIUM": 10, "HIGH": 20}.get(pain, 0)
    score += {"NONE": 0, "MEDIUM": 5, "HIGH": 10}.get(timing, 0)
    score += 7 if dm == "LIKELY" else 0
    score += calculate_specificity_bonus(all_text)

    caps = {"NONE": 30, "MEDIUM": 75, "HIGH": 90, "VERY HIGH": 100}
    score = min(score, caps.get(intent, 30))

    # GATE de ICP:
    if icp == "UNKNOWN":
        score = min(score, 55)
    if icp == "OUT":
        return {
            "icp": icp, "intent": intent, "need": need, "pain": pain,
            "trigger": trigger, "dm": dm, "timing": timing,
            "score": 0, "confidence": "LOW", "classification": "IGNORE"
        }

    # GATE COMERCIAL: oportunidade real exige ICP + Buying Intent + demanda/dor.
    # Trigger isolado, notícia, contratação de pessoa ou tecnologia genérica = WATCH.
    if icp == "UNKNOWN":
        classification = "WATCH" if any(x != "NONE" for x in [intent, need, pain, trigger]) else "IGNORE"
    elif intent == "HIGH" and need in ("MEDIUM", "HIGH") and pain in ("MEDIUM", "HIGH") and score >= 80:
        classification = "HOT"
    elif intent == "HIGH" and need in ("MEDIUM", "HIGH") and (pain != "NONE") and score >= 60:
        classification = "WARM"
    elif intent == "MEDIUM" and need in ("MEDIUM", "HIGH"):
        classification = "WATCH"
    elif pain != "NONE" or trigger != "NONE" or need != "NONE":
        classification = "WATCH"
    else:
        classification = "IGNORE"

    confidence = "HIGH" if intent in ("HIGH", "VERY HIGH") and need != "NONE" else ("MEDIUM" if any(x != "NONE" for x in [intent, need, pain]) else "LOW")

    return {
        "icp": icp, "intent": intent, "need": need, "pain": pain,
        "trigger": trigger, "dm": dm, "timing": timing,
        "score": int(score), "confidence": confidence, "classification": classification
    }

# ============================================================
# HUNTER
# ============================================================

def qualify_hunter(conn):
    companies = conn.execute("SELECT * FROM companies ORDER BY id").fetchall()
    stats = {"new": 0, "updated": 0}

    for c in companies:
        rows = conn.execute("""
            SELECT s.*, src.title, src.url, src.source_type
            FROM signals s
            LEFT JOIN sources src ON src.id=s.source_id
            WHERE s.company_id=?
        """, (c["id"],)).fetchall()

        signals = [dict(r) for r in rows]
        if not signals:
            continue

        result = classify_company(c["name"], signals)
        now = datetime.utcnow().isoformat(timespec="seconds")

        reason = (
            f"ICP={result['icp']} | Intent={result['intent']} | Need={result['need']} | "
            f"Pain={result['pain']} | Trigger={result['trigger']} | Timing={result['timing']} | "
            f"DM={result['dm']} | Score={result['score']}"
        )
        next_action = {
            "HOT": "Abordagem comercial imediata com validação de dor e decisão.",
            "WARM": "Abordagem consultiva e confirmação de necessidade.",
            "WATCH": "Monitorar novas evidências e buscar confirmação de dor/intent.",
            "IGNORE": "Sem ação comercial neste momento.",
        }[result["classification"]]

        exists = conn.execute("SELECT id FROM opportunities WHERE company_id=?", (c["id"],)).fetchone()
        vals = (
            next((s["evidence"] for s in signals if s["kind"] == "BUSINESS_TRIGGER"), ""),
            next((s["evidence"] for s in signals if s["kind"] == "NEED_SIGNAL"), ""),
            next((s["evidence"] for s in signals if s["kind"] == "PAIN_RISK"), ""),
            result["intent"],
            next((s["evidence"] for s in signals if s["kind"] == "DECISION_MAKER"), ""),
            result["timing"], result["score"], result["confidence"],
            result["classification"], next_action, reason, now
        )

        if exists:
            conn.execute("""UPDATE opportunities SET trigger_text=?,need=?,pain=?,intent=?,dm=?,timing=?,
                score=?,confidence=?,classification=?,next_action=?,reason=?,updated_at=? WHERE company_id=?""",
                vals + (c["id"],))
            stats["updated"] += 1
        else:
            conn.execute("""INSERT INTO opportunities(company_id,trigger_text,need,pain,intent,dm,timing,
                score,confidence,classification,next_action,reason,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c["id"],) + vals + (now,))
            stats["new"] += 1

        conn.execute("UPDATE companies SET icp=?,updated_at=? WHERE id=?", (result["icp"], now, c["id"]))

    conn.commit()
    return stats

# ============================================================
# CAÇA
# ============================================================

def reprocess_unassigned_sources(conn, diag, limit=1000):
    """Reexecuta somente a resolução de entidade sobre fontes já coletadas.

    Isso permite corrigir as 616/637 evidências antigas sem depender de uma nova coleta.
    """
    rows = conn.execute("""
        SELECT id,company_id,title,url,source_type,publisher,content
        FROM sources
        WHERE company_id IS NULL
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    if not rows:
        return 0, 0

    existing = [r["name"] for r in conn.execute("SELECT name FROM companies ORDER BY id").fetchall()]
    resolved = 0
    for row in rows:
        diag["reprocessed"] += 1
        if not is_direct_b2b_source(row["url"] or "", row["title"] or "", row["content"] or ""):
            continue
        name, origin, _ = resolve_company(
            row["title"] or "", row["content"] or "", row["publisher"] or "",
            row["url"] or "", "", existing, diag
        )
        if not name:
            continue
        company_id = find_or_create_company(conn, name, datetime.utcnow().isoformat(timespec="seconds"), diag)
        if not company_id:
            continue
        conn.execute("UPDATE sources SET company_id=? WHERE id=?", (company_id, row["id"]))
        conn.execute("UPDATE signals SET company_id=? WHERE source_id=? AND company_id IS NULL", (company_id, row["id"]))
        if name not in existing:
            existing.append(name)
        resolved += 1
        diag["reprocessed_resolved"] += 1
    conn.commit()
    return len(rows), resolved

def run_hunt():
    conn = db()
    started = datetime.utcnow().isoformat(timespec="seconds")
    diag = empty_diag()

    # Primeiro recupera o estoque já coletado e ainda sem empresa.
    # Isso evita que a evolução do resolver exija nova coleta para surtir efeito.
    reprocess_unassigned_sources(conn, diag, limit=1500)

    collected = []
    seen = set()

    progress = st.progress(0, text="MILO coletando fontes...")
    total_q = len(SEARCH_QUERIES)

    for i, q in enumerate(SEARCH_QUERIES):
        for item in rss_search(q):
            key = item["url"]
            if key not in seen:
                seen.add(key)
                collected.append(item)
        progress.progress(int((i + 1) / total_q * 60), text=f"MILO: consulta {i+1}/{total_q}")

    # PNCP/GOV/LICITAÇÃO foram retirados da caça comercial.
    # O Hunter é B2B privado: não transforma compras públicas em oportunidade TECHS.
    collected = [
        item for item in collected
        if not is_excluded_source(item.get("url", ""), item.get("title", "") + " " + item.get("body", ""))
    ]

    diag["sources"] = len(collected)

    existing = [r["name"] for r in conn.execute("SELECT name FROM companies").fetchall()]
    signals_new = 0
    companies_touched = set()
    unassigned = 0

    # Limite inicial para não transformar o Cloud em centenas de requests sequenciais.
    candidates = []
    for item in collected:
        text = f"{item.get('title','')} {item.get('body','')}"
        # Notícias são apenas descoberta e não entram no funil comercial.
        # Processamos somente URLs que possam representar evidência B2B direta.
        if is_direct_b2b_source(item.get("url", ""), item.get("title", ""), item.get("body", "")) and term_hits(text, INTENT_STRONG + TECH_TERMS + TRIGGER_TERMS + PAIN_TERMS):
            candidates.append(item)

    max_candidates = min(len(candidates), 250)
    progress = st.progress(60, text=f"Processando {max_candidates} fontes candidatas...")

    for idx, item in enumerate(candidates[:max_candidates]):
        title = clean_text(item.get("title", ""))
        url = item.get("url", "")
        body = clean_text(item.get("body", ""))
        source_type = item.get("source_type", "NEWS")
        publisher = item.get("publisher", "")
        explicit = item.get("company_candidate", "")

        # Enriquecimento somente quando necessário.
        full_body = fetch_page(url) if len(body) < 700 else body
        evidence_text = f"{title}. {full_body or body}"

        name, origin, resolve_reason = resolve_company(
            title, evidence_text, publisher, url, explicit, existing, diag
        )

        company_id = None
        if name:
            company_id = find_or_create_company(conn, name, datetime.utcnow().isoformat(timespec="seconds"), diag)
            if company_id:
                companies_touched.add(company_id)
                if name not in existing:
                    existing.append(name)

        # Fonte é armazenada mesmo sem empresa: MILO não perde evidência.
        try:
            now_iso = datetime.utcnow().isoformat(timespec="seconds")
            existing_source = conn.execute("SELECT id,company_id FROM sources WHERE url=?", (url,)).fetchone()
            if existing_source:
                source_id = existing_source["id"]
                # Corrige registros antigos que foram armazenados sem empresa.
                if company_id and not existing_source["company_id"]:
                    conn.execute("UPDATE sources SET company_id=?,title=?,publisher=?,content=?,published_at=?,query=? WHERE id=?",
                                 (company_id, title, publisher, evidence_text[:12000], item.get("published_at",""), item.get("query",""), source_id))
                    conn.execute("UPDATE signals SET company_id=? WHERE source_id=? AND company_id IS NULL",
                                 (company_id, source_id))
                else:
                    conn.execute("UPDATE sources SET content=?,title=?,publisher=? WHERE id=?",
                                 (evidence_text[:12000], title, publisher, source_id))
            else:
                cur = conn.execute("""INSERT INTO sources
                    (company_id,title,url,source_type,publisher,collected_at,content,published_at,query)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (company_id, title, url, source_type, publisher, now_iso,
                     evidence_text[:12000], item.get("published_at",""), item.get("query","")))
                source_id = cur.lastrowid
            conn.commit()
        except Exception:
            source_id = None

        # Sinais do MILO.
        kinds = classify_signal_type(evidence_text)
        generated = []

        direct_source = is_direct_b2b_source(url, title, evidence_text)
        if not direct_source:
            # Descoberta sem valor comercial final: fonte é preservada, mas não gera sinal.
            continue
        intent_conf = validate_buying_intent(evidence_text, source_type, direct_source=direct_source)
        if intent_conf != "NONE":
            for ev in evidence_snippets(evidence_text, INTENT_STRONG + INTENT_CONTEXT, 2):
                generated.append(("BUYING_INTENT", ev, intent_conf))

        for kind, terms in [
            ("NEED_SIGNAL", TECH_TERMS),
            ("BUSINESS_TRIGGER", TRIGGER_TERMS),
            ("PAIN_RISK", PAIN_TERMS),
            ("DECISION_MAKER", DM_TERMS),
        ]:
            for ev in evidence_snippets(evidence_text, terms, 2):
                generated.append((kind, ev, "MEDIUM"))

        generated = filter_signals([
            {"kind": k, "evidence": e, "confidence": c}
            for k, e, c in generated
        ])

        for s in generated:
            try:
                conn.execute("""INSERT OR IGNORE INTO signals
                    (company_id,source_id,kind,evidence,evidence_type,confidence,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (company_id, source_id, s["kind"], s["evidence"], "FACT", s["confidence"],
                     datetime.utcnow().isoformat(timespec="seconds")))
                if conn.execute("SELECT changes()").fetchone()[0] > 0:
                    signals_new += 1
                    if company_id:
                        diag["signals_with_company"] += 1
                    else:
                        diag["signals_without_company"] += 1
            except Exception:
                pass

        diag["signals_total"] += len(generated)
        if not company_id and generated:
            unassigned += len(generated)

        if idx % 10 == 0:
            progress.progress(60 + int((idx + 1) / max(1, max_candidates) * 40),
                              text=f"Processando {idx+1}/{max_candidates}...")

    progress.empty()

    stats = qualify_hunter(conn)

    finished = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("""INSERT INTO hunts
        (started_at,finished_at,sources_found,signals_found,companies_found,new_opportunities,
         updated_opportunities,unassigned,discarded)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (started, finished, len(collected), signals_new, len(companies_touched),
         stats["new"], stats["updated"], unassigned, 0))
    conn.commit()

    return diag, len(collected), signals_new, len(companies_touched), stats, unassigned

# ============================================================
# UI
# ============================================================

conn = db()

st.title("🔎 HUNTER TECHS")
st.caption("MILO → evidência pública → resolução de entidade → HUNTER → qualificação comercial")

cols = st.columns(5)
companies_count = conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"]
signals_count = conn.execute("SELECT COUNT(*) c FROM signals").fetchone()["c"]
opp_count = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification IN ('HOT','WARM')").fetchone()["c"]
hot_count = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification='HOT'").fetchone()["c"]
warm_count = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification='WARM'").fetchone()["c"]

cols[0].metric("Empresas", companies_count)
cols[1].metric("Sinais", signals_count)
cols[2].metric("Oportunidades", opp_count)
cols[3].metric("HOT", hot_count)
cols[4].metric("WARM", warm_count)
watch_count = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE classification='WATCH'").fetchone()["c"]
st.caption(f"WATCH / monitoramento: {watch_count} | Oportunidade comercial: somente HOT + WARM")

if st.button("🚀 IR PARA CAÇA", type="primary", use_container_width=True):
    with st.spinner("Caça em andamento..."):
        diag, sources, sigs, comps, stats, unassigned = run_hunt()

    st.success(
        f"Caça concluída — {sources} fontes | {sigs} sinais novos | "
        f"{comps} empresas | {stats['new']} novas oportunidades | "
        f"{stats['updated']} atualizadas | {unassigned} sinais sem empresa"
    )

    st.subheader("🔬 Diagnóstico MILO → Empresa")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Candidatos extraídos", diag["candidate_extracted"])
    d2.metric("Empresas resolvidas", diag["resolved_existing"] + diag["resolved_new"])
    d3.metric("Não resolvidos", diag["not_resolved"])
    d4.metric("Sinais sem empresa", diag["signals_without_company"])
    st.caption(f"Reprocessamento do estoque: {diag['reprocessed']} fontes antigas analisadas → {diag['reprocessed_resolved']} resolvidas.")

    st.write("**Origem dos candidatos encontrados**")
    st.dataframe(pd.DataFrame([{
        "Explícito/PNCP": diag["explicit_candidate"],
        "Título": diag["title_candidate"],
        "Corpo": diag["body_candidate"],
        "Domínio (diagnóstico)": diag["domain_candidate"],
    }]), use_container_width=True, hide_index=True)

    st.write("**Funil de resolução**")
    st.dataframe(pd.DataFrame([{
        "Fontes": diag["sources"],
        "Candidatos": diag["candidate_extracted"],
        "Resolvidas": diag["resolved_existing"] + diag["resolved_new"],
        "Não resolvidas": diag["not_resolved"],
        "Sinais": diag["signals_total"],
        "Sinais com empresa": diag["signals_with_company"],
        "Sinais sem empresa": diag["signals_without_company"],
    }]), use_container_width=True, hide_index=True)

    if diag["examples"]:
        st.write("**Amostra das falhas de resolução**")
        st.dataframe(pd.DataFrame(diag["examples"]), use_container_width=True, hide_index=True)

tab1, tab2, tab3, tab4 = st.tabs(["🎯 Oportunidades", "🧠 Sinais do Milo", "🏢 Empresas", "📊 Histórico"])

with tab1:
    rows = conn.execute("""
        SELECT o.*, c.name company, c.icp
        FROM opportunities o JOIN companies c ON c.id=o.company_id
        WHERE o.classification IN ('HOT','WARM')
        ORDER BY o.score DESC, o.updated_at DESC
    """).fetchall()
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma oportunidade qualificada ainda.")

with tab2:
    rows = conn.execute("""
        SELECT s.id,c.name company,s.kind,s.confidence,s.evidence,
               src.title,src.publisher,src.url,src.source_type,src.collected_at
        FROM signals s
        LEFT JOIN companies c ON c.id=s.company_id
        LEFT JOIN sources src ON src.id=s.source_id
        ORDER BY s.id DESC
        LIMIT 1000
    """).fetchall()
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Exportar sinais CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            "hunter_techs_sinais.csv",
            "text/csv",
        )
    else:
        st.info("Nenhum sinal registrado.")

with tab3:
    rows = conn.execute("SELECT id,name,website,icp,created_at,updated_at FROM companies ORDER BY name").fetchall()
    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma empresa resolvida.")

with tab4:
    rows = conn.execute("SELECT * FROM hunts ORDER BY id DESC LIMIT 20").fetchall()
    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma caça registrada.")

st.divider()
st.caption("V11 — Caça B2B privada: notícias, governo e licitações não entram como oportunidade. WATCH é monitoramento; oportunidade comercial exige Buying Intent + Need/Pain.")
