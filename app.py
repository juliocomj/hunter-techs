import io
import re
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================
# HUNTER TECHS
# MILO -> VALIDATOR -> ENTITY -> HUNTER
# Single-file version
# ============================================================

st.set_page_config(
    page_title="HUNTER TECHS",
    page_icon="🔎",
    layout="wide"
)

DB = "hunter.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126 Safari/537.36 TECHS-Hunter/10.0"
    )
}


# ============================================================
# CONFIGURAÇÃO MILO
# ============================================================

SEARCH_QUERIES = [
    '"RFP" "segurança da informação"',
    '"RFQ" segurança',
    '"request for proposal" tecnologia',
    '"request for quotation" tecnologia',
    '"solicitação de proposta" "serviços de TI"',
    '"solicitação de cotação" tecnologia',
    '"processo de contratação" TI',
    '"busca de fornecedor" tecnologia',
    '"seleção de fornecedor" TI',
    '"contratação" "serviços gerenciados"',
    '"contratação" cibersegurança',
    '"contratação" backup tecnologia',
    '"contratação" monitoramento TI',
    '"contratação de empresa" segurança tecnologia',

    '"novo CIO" empresa',
    '"novo CTO" empresa',
    '"novo diretor de tecnologia"',
    '"novo diretor de TI"',
    '"novo gerente de TI"',
    '"head de tecnologia" empresa',

    '"migração para cloud" empresa',
    '"migração para nuvem" empresa',
    '"modernização da infraestrutura" empresa',
    '"transformação digital" empresa',
    '"projeto de infraestrutura" empresa',
    '"data center" expansão empresa',

    '"abriu novas unidades" empresa',
    '"novas lojas" expansão empresa',
    '"nova filial" empresa',
    '"aquisição" empresa tecnologia',
    '"fusão" empresa tecnologia',

    'ransomware empresa',
    '"incidente de segurança" empresa',
    '"ataque cibernético" empresa',
    '"vulnerabilidade" empresa segurança',
    '"vazamento de dados" empresa',

    '"monitoramento 24x7" empresa',
    '"continuidade de negócios" empresa tecnologia',
    '"disaster recovery" empresa',
    '"proteção de endpoints" empresa',
    '"gestão de endpoints" empresa',
    '"SOC" empresa contratação',
]


INTENT_STRONG = [
    "rfp",
    "rfq",
    "request for proposal",
    "request for quotation",
    "solicitação de proposta",
    "solicitação de cotação",
    "processo de contratação",
    "contratação de fornecedor",
    "busca de fornecedor",
    "busca por fornecedor",
    "seleção de fornecedor",
    "fornecedores interessados",
    "convidou fornecedores",
    "edital",
    "licitação",
    "licitacao",
    "pregão",
    "pregao",
    "concorrência",
    "concorrencia",
    "tomada de preços",
    "tomada de precos",
    "troca de fornecedor",
    "busca de parceiro",
    "contratação de empresa",
]


INTENT_CONTEXT = [
    "cotação",
    "cotacao",
    "orçamento",
    "orcamento",
    "comprar",
    "aquisição",
    "aquisicao",
    "contratar",
]


NEED_TERMS = [
    "rmm",
    "edr",
    "backup",
    "segurança da informação",
    "segurança cibernética",
    "seguranca cibernetica",
    "cibersegurança",
    "ciberseguranca",
    "cybersecurity",
    "monitoramento de infraestrutura",
    "monitoramento de ti",
    "gestão de endpoints",
    "gestao de endpoints",
    "endpoint",
    "firewall",
    "sase",
    "serviços gerenciados",
    "servicos gerenciados",
    "managed services",
    "infraestrutura de ti",
    "infraestrutura tecnológica",
    "infraestrutura tecnologica",
    "cloud",
    "nuvem",
    "continuidade",
    "disaster recovery",
    "recuperação de desastre",
    "recuperacao de desastre",
    "governança de ti",
    "governanca de ti",
    "observabilidade",
    "soc",
    "mssp",
    "backup em nuvem",
    "proteção de endpoints",
    "protecao de endpoints",
]


TRIGGER_TERMS = [
    "novo cio",
    "novo cto",
    "novo diretor de ti",
    "novo diretor de tecnologia",
    "novo gerente de ti",
    "head de tecnologia",
    "expansão",
    "expansao",
    "nova unidade",
    "nova filial",
    "aquisição",
    "aquisicao",
    "fusão",
    "fusao",
    "crescimento",
    "transformação digital",
    "transformacao digital",
    "migração para cloud",
    "migração para nuvem",
    "implantação de erp",
    "implantacao de erp",
    "incidente de segurança",
    "incidente de seguranca",
    "ataque cibernético",
    "ataque cibernetico",
    "reestruturação de ti",
    "reestruturacao de ti",
    "modernização da infraestrutura",
    "modernizacao da infraestrutura",
    "novas lojas",
    "novas unidades",
    "data center",
    "novo centro de distribuição",
    "novo centro de distribuicao",
    "abertura de unidades",
]


PAIN_TERMS = [
    "indisponibilidade",
    "downtime",
    "parada",
    "falha",
    "incidente",
    "ataque",
    "vulnerabilidade",
    "risco",
    "interrupção",
    "interrupcao",
    "perda de dados",
    "vazamento",
    "ransomware",
    "obsolescência",
    "obsolescencia",
    "falta de equipe",
    "sobrecarga",
    "24x7",
    "tempo de resposta",
    "indisponível",
    "indisponivel",
]


DM_TERMS = [
    "cio",
    "cto",
    "diretor de ti",
    "diretor de tecnologia",
    "gerente de ti",
    "gerente de tecnologia",
    "head de tecnologia",
    "diretor de infraestrutura",
    "diretor de segurança",
    "chief information officer",
    "chief technology officer",
]


TECH_TERMS = set(
    NEED_TERMS
    + [
        "ti",
        "tecnologia",
        "infraestrutura",
        "segurança",
        "seguranca",
        "cloud",
        "dados",
    ]
)


MEDIA_NAMES = {
    "google news",
    "google",
    "youtube",
    "facebook",
    "linkedin",
    "reuters",
    "exame",
    "valor",
    "estadao",
    "estadião",
    "folha",
    "globo",
    "uol",
    "terra",
    "cnn",
    "forbes",
    "g1",
    "canaltech",
    "tecmundo",
    "olhar digital",
    "infomoney",
    "istoé",
    "isto é",
    "news",
    "metropoles",
    "bloomberg",
    "moneytimes",
    "startups",
    "ti inside",
    "teletime",
    "convergencia digital",
}


MEDIA_DOMAINS = {
    "news.google.com",
    "g1.globo.com",
    "exame.com",
    "valor.globo.com",
    "uol.com.br",
    "terra.com.br",
    "estadao.com.br",
    "folha.uol.com.br",
    "oglobo.globo.com",
    "cnnbrasil.com.br",
    "forbes.com.br",
    "canaltech.com.br",
    "tecmundo.com.br",
    "olhardigital.com.br",
    "infomoney.com.br",
    "metropoles.com",
    "teletime.com.br",
    "convergenciadigital.com.br",
    "startups.com.br",
    "moneytimes.com.br",
}


LEGAL_SUFFIX = re.compile(
    r"\b(S\.?A\.?|S/A|LTDA|Ltda\.?|Holding|Holdings|Corp\.?|Inc\.?|Group|Grupo)\b",
    re.I
)


# ============================================================
# UTILITÁRIOS
# ============================================================

def now():
    return datetime.now().isoformat(timespec="seconds")


def norm(value):
    return re.sub(r"\s+", " ", (value or "")).strip()


def term_hits(text, terms):
    low = norm(text).lower()
    return [term for term in terms if term.lower() in low]


def source_domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


# ============================================================
# ENTITY RESOLUTION
# ============================================================

def clean_company(name):
    if not name:
        return ""

    name = norm(name)

    name = name.strip(
        " -–—:,.()[]\"'"
    )

    name = re.sub(
        r"^(?:a|o|as|os|da|do|na|no)\s+",
        "",
        name,
        flags=re.I
    )

    name = re.sub(
        r"\s+(?:anuncia|anunciou|contrata|contratou|busca|buscou|"
        r"expande|expandiu|abre|abriu|projeta|prevê|preve|"
        r"investe|investiu|vai|inicia|iniciou|adota|adotou|"
        r"lança|lancou|lançou|moderniza|modernizou|"
        r"implementa|implementou|migra|migrou|"
        r"seleciona|selecionou|procura|procurou|"
        r"planeja|planejou).*$",
        "",
        name,
        flags=re.I
    )

    return name.strip(" -–—:,.()[]\"'")


def validate_company_name(name):
    if not name:
        return False

    n = clean_company(name)
    low = n.lower()

    if len(n) < 3 or len(n) > 110:
        return False

    if len(n.split()) > 10:
        return False

    if low in MEDIA_NAMES:
        return False

    if any(low.startswith(x + " ") for x in MEDIA_NAMES):
        return False

    if re.fullmatch(r"[0-9 .,%/-]+", n):
        return False

    invalid = {
        "empresa",
        "companhia",
        "grupo",
        "organização",
        "organizacao",
        "tecnologia",
        "segurança",
        "seguranca",
        "infraestrutura",
        "mercado",
        "dados",
    }

    if low in invalid:
        return False

    return True


def existing_company_match(text, companies):
    low = norm(text).lower()

    matches = []

    for company in companies:
        name = norm(company.get("name", ""))

        if len(name) < 4:
            continue

        if name.lower() in low:
            matches.append(name)

    if not matches:
        return None

    matches.sort(
        key=lambda x: len(x),
        reverse=True
    )

    return matches[0]


def extract_company(
    title,
    body,
    publisher,
    explicit_candidate=None,
    url=""
):
    """
    Entity resolver determinístico.
    Não usa API paga.
    """

    if explicit_candidate:
        candidate = clean_company(explicit_candidate)

        if validate_company_name(candidate):
            return candidate

    # Buscar empresas já conhecidas primeiro.
    try:
        con = sqlite3.connect(DB)

        rows = con.execute(
            "SELECT name FROM companies LIMIT 3000"
        ).fetchall()

        con.close()

        companies = [
            {"name": row[0]}
            for row in rows
        ]

        match = existing_company_match(
            title + " " + body[:10000],
            companies
        )

        if match:
            return match

    except Exception:
        pass

    title = norm(title)
    body = norm(body)

    # --------------------------------------------------------
    # Sujeito antes de verbo comercial
    # --------------------------------------------------------

    verbs = (
        r"anuncia|anunciou|contrata|contratou|busca|buscou|"
        r"expande|expandiu|abre|abriu|projeta|prevê|preve|"
        r"investe|investiu|inicia|iniciou|adota|adotou|"
        r"lança|lancou|lançou|moderniza|modernizou|"
        r"implementa|implementou|migra|migrou|"
        r"seleciona|selecionou|procura|procurou|"
        r"planeja|planejou"
    )

    pattern = rf"^(.{{3,100}}?)\s+(?:{verbs})\b"

    match = re.search(
        pattern,
        title,
        flags=re.I
    )

    if match:
        candidate = clean_company(
            match.group(1)
        )

        if (
            validate_company_name(candidate)
            and candidate.lower() != norm(publisher).lower()
        ):
            return candidate

    # --------------------------------------------------------
    # Empresa / Grupo / Holding
    # --------------------------------------------------------

    patterns = [
        r"\b((?:Empresa|Grupo|Holding|Companhia)\s+"
        r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][^,.;:]{2,90})",

        r"\b([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][\wÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç&.'/-]*"
        r"(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][\wÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç&.'/-]*){0,6})"
        r"\s+(?:S\.?A\.?|S/A|LTDA|Holding|Holdings)\b"
    ]

    combined = title + " " + body[:10000]

    for pattern in patterns:
        match = re.search(
            pattern,
            combined
        )

        if match:
            candidate = clean_company(
                match.group(1)
            )

            if validate_company_name(candidate):
                return candidate

    # --------------------------------------------------------
    # Sequência de nomes próprios
    # --------------------------------------------------------

    proper_pattern = (
        r"\b("
        r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]"
        r"[A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç0-9&.'/-]*"
        r"(?:\s+"
        r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]"
        r"[A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç0-9&.'/-]*"
        r"){0,5}"
        r")\b"
    )

    candidates = []

    for match in re.finditer(
        proper_pattern,
        title + " " + body[:3500]
    ):
        candidate = clean_company(
            match.group(1)
        )

        if not validate_company_name(candidate):
            continue

        if candidate.lower() == norm(publisher).lower():
            continue

        score = 0

        if LEGAL_SUFFIX.search(candidate):
            score += 30

        if len(candidate.split()) >= 2:
            score += 10

        if candidate.lower() in title.lower():
            score += 20

        candidates.append(
            (score, candidate)
        )

    if candidates:
        candidates.sort(
            key=lambda x: (-x[0], len(x[1]))
        )

        return candidates[0][1]

    # --------------------------------------------------------
    # Domínio somente como último recurso.
    # Nunca mídia / governo.
    # --------------------------------------------------------

    domain = source_domain(url)

    if (
        domain
        and domain not in MEDIA_DOMAINS
        and not domain.endswith(".gov.br")
        and not domain.endswith(".jus.br")
        and not domain.endswith(".leg.br")
        and not domain.endswith(".edu.br")
    ):
        root = domain.split(".")[0]

        if (
            len(root) >= 4
            and root.lower() not in MEDIA_NAMES
            and root.lower() not in {
                "www",
                "blog",
                "portal",
                "site",
            }
        ):
            candidate = root.replace(
                "-",
                " "
            ).title()

            if validate_company_name(candidate):
                return candidate

    return None


# ============================================================
# SIGNAL VALIDATOR
# ============================================================

NEGATIVE_PATTERNS = [
    "não pretende",
    "nao pretende",
    "não vai contratar",
    "nao vai contratar",
    "não contratará",
    "nao contratara",
    "sem intenção de contratar",
    "sem intencao de contratar",
    "descarta contratação",
    "descarta contratacao",
    "cancelou a contratação",
    "cancelou a contratacao",
    "contratação foi cancelada",
    "contratacao foi cancelada",
]


HIRING_PATTERNS = [
    "vaga",
    "vagas",
    "recrutamento",
    "processo seletivo",
    "contratando",
    "seleção de profissionais",
    "seleciona profissionais",
    "headcount",
]


SPECIFICITY_TERMS = [
    "rmm",
    "edr",
    "backup",
    "backup em nuvem",
    "monitoramento 24x7",
    "monitoramento de infraestrutura",
    "gestão de endpoints",
    "proteção de endpoints",
    "firewall",
    "sase",
    "soc",
    "mssp",
    "disaster recovery",
    "recuperação de desastre",
    "fornecedores interessados",
    "edital",
    "rfp",
    "rfq",
    "quantidade de equipamentos",
    "endpoints",
    "usuários",
    "data center",
    "sla",
    "24x7",
]


def has_negative_keywords(text):
    low = norm(text).lower()

    return any(
        term in low
        for term in NEGATIVE_PATTERNS
    )


def is_hiring_signal(text):
    low = norm(text).lower()

    if "vaga de fornecedor" in low:
        return False

    return any(
        term in low
        for term in HIRING_PATTERNS
    )


def validate_buying_intent(text):
    low = norm(text).lower()

    if has_negative_keywords(low):
        return False

    if is_hiring_signal(low):
        return False

    # Intenção forte.
    if any(
        term in low
        for term in INTENT_STRONG
    ):
        return True

    # Termos genéricos só valem com contexto técnico.
    generic = any(
        term in low
        for term in INTENT_CONTEXT
    )

    technical = any(
        term in low
        for term in TECH_TERMS
    )

    return generic and technical


def classify_signal_type(text):
    low = norm(text).lower()

    if not low:
        return "NOISE"

    if is_hiring_signal(low):
        if not validate_buying_intent(low):
            return "NOISE"

    if validate_buying_intent(low):
        return "BUYING_INTENT"

    if any(
        term in low
        for term in SPECIFICITY_TERMS
    ):
        return "TECHNICAL_NEED"

    if any(
        term in low
        for term in TRIGGER_TERMS
    ):
        return "BUSINESS_TRIGGER"

    if any(
        term in low
        for term in PAIN_TERMS
    ):
        return "PAIN_RISK"

    return "OTHER"


def extract_timeline(text):
    low = norm(text).lower()

    if any(
        x in low
        for x in [
            "imediato",
            "urgente",
            "nos próximos dias",
            "nos proximos dias",
        ]
    ):
        return "HIGH"

    if any(
        x in low
        for x in [
            "este mês",
            "este mes",
            "próximo mês",
            "proximo mes",
            "nos próximos 30 dias",
            "nos proximos 30 dias",
            "até o fim do mês",
            "ate o fim do mes",
        ]
    ):
        return "HIGH"

    if any(
        x in low
        for x in [
            "neste trimestre",
            "neste ano",
            "próximos meses",
            "proximos meses",
            "em breve",
        ]
    ):
        return "MEDIUM"

    return "NONE"


def extract_specificity_signals(text):
    low = norm(text).lower()

    return sorted(
        {
            term
            for term in SPECIFICITY_TERMS
            if term in low
        }
    )


def calculate_specificity_bonus(signals):
    found = set()

    for signal in signals:
        found.update(
            extract_specificity_signals(
                signal.get("evidence", "")
            )
        )

    return min(
        len(found) * 2,
        8
    )


def filter_signals(signals):
    result = []
    seen = set()

    for signal in signals or []:

        evidence = norm(
            signal.get("evidence", "")
        )

        kind = signal.get(
            "kind",
            ""
        )

        if not evidence:
            continue

        key = (
            kind,
            signal.get("source_id"),
            evidence.lower()
        )

        if key in seen:
            continue

        if has_negative_keywords(evidence):
            continue

        if kind == "BUYING_INTENT":

            if is_hiring_signal(evidence):
                continue

            if not validate_buying_intent(evidence):
                continue

        seen.add(key)
        result.append(signal)

    return result


# ============================================================
# EVIDÊNCIAS
# ============================================================

def evidence_snippets(
    text,
    terms,
    max_items=4
):
    text = norm(text)

    if not text:
        return []

    low = text.lower()

    result = []
    seen = set()

    for term in sorted(
        set(terms),
        key=len,
        reverse=True
    ):
        start = 0

        while True:

            index = low.find(
                term.lower(),
                start
            )

            if index < 0:
                break

            left = max(
                0,
                index - 240
            )

            right = min(
                len(text),
                index + len(term) + 360
            )

            snippet = norm(
                text[left:right]
            ).strip(
                " -–—"
            )

            key = snippet.lower()

            if (
                len(snippet) >= 45
                and key not in seen
            ):
                result.append(snippet)
                seen.add(key)

            start = index + len(term)

            if len(result) >= max_items:
                return result

    return result


# ============================================================
# BANCO
# ============================================================

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS companies(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            website TEXT,
            icp TEXT DEFAULT 'UNKNOWN',
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sources(
            id INTEGER PRIMARY KEY,
            company_id INTEGER NULL,
            title TEXT,
            url TEXT UNIQUE,
            source_type TEXT DEFAULT 'NEWS',
            publisher TEXT,
            collected_at TEXT,
            content TEXT,
            published_at TEXT,
            query TEXT
        );

        CREATE TABLE IF NOT EXISTS signals(
            id INTEGER PRIMARY KEY,
            company_id INTEGER NULL,
            source_id INTEGER NULL,
            kind TEXT,
            evidence TEXT,
            evidence_type TEXT,
            confidence TEXT DEFAULT 'MEDIUM',
            created_at TEXT,
            UNIQUE(
                source_id,
                kind,
                evidence
            )
        );

        CREATE TABLE IF NOT EXISTS opportunities(
            id INTEGER PRIMARY KEY,
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
        );

        CREATE TABLE IF NOT EXISTS hunts(
            id INTEGER PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT,
            status TEXT,
            sources_found INTEGER DEFAULT 0,
            signals_found INTEGER DEFAULT 0,
            companies INTEGER DEFAULT 0,
            new_opps INTEGER DEFAULT 0,
            updated_opps INTEGER DEFAULT 0,
            discarded INTEGER DEFAULT 0,
            unassigned_signals INTEGER DEFAULT 0
        );
        """
    )

    migrations = [
        (
            "signals",
            "confidence",
            "TEXT DEFAULT 'MEDIUM'"
        ),
        (
            "sources",
            "published_at",
            "TEXT"
        ),
        (
            "sources",
            "query",
            "TEXT"
        ),
        (
            "hunts",
            "unassigned_signals",
            "INTEGER DEFAULT 0"
        ),
    ]

    for table, column, data_type in migrations:

        columns = {
            row[1]
            for row in con.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }

        if column not in columns:
            con.execute(
                f"ALTER TABLE {table} "
                f"ADD COLUMN {column} {data_type}"
            )

    # Limpeza somente de empresas conhecidas como mídia.
    for media in MEDIA_NAMES:

        con.execute(
            """
            DELETE FROM opportunities
            WHERE company_id IN (
                SELECT id
                FROM companies
                WHERE lower(name)=?
            )
            """,
            (media,)
        )

        con.execute(
            """
            DELETE FROM signals
            WHERE company_id IN (
                SELECT id
                FROM companies
                WHERE lower(name)=?
            )
            """,
            (media,)
        )

        con.execute(
            """
            DELETE FROM sources
            WHERE company_id IN (
                SELECT id
                FROM companies
                WHERE lower(name)=?
            )
            """,
            (media,)
        )

        con.execute(
            """
            DELETE FROM companies
            WHERE lower(name)=?
            """,
            (media,)
        )

    con.commit()

    return con


# ============================================================
# GOOGLE NEWS
# ============================================================

def rss_search(query):

    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "xml"
        )

        result = []

        for item in soup.find_all("item"):

            link = (
                item.link.get_text(
                    strip=True
                )
                if item.link
                else ""
            )

            if not link:
                continue

            description = ""

            if item.description:
                description = BeautifulSoup(
                    item.description.get_text(
                        " ",
                        strip=True
                    ),
                    "html.parser"
                ).get_text(
                    " ",
                    strip=True
                )

            result.append(
                {
                    "title": norm(
                        item.title.get_text(
                            " ",
                            strip=True
                        )
                        if item.title
                        else ""
                    ),
                    "url": link,
                    "description": norm(
                        description
                    ),
                    "published": norm(
                        item.pubDate.get_text(
                            " ",
                            strip=True
                        )
                        if item.pubDate
                        else ""
                    ),
                    "publisher": norm(
                        item.source.get_text(
                            " ",
                            strip=True
                        )
                        if item.source
                        else ""
                    ),
                    "source_type": "NEWS",
                    "query": query,
                }
            )

        return result[:20]

    except Exception:
        return []


# ============================================================
# PNCP
# ============================================================

def pncp_search(
    pages=6,
    days_forward=30
):

    base = (
        "https://pncp.gov.br/"
        "api/consulta/v1/contratacoes/proposta"
    )

    final_date = (
        datetime.now()
        + timedelta(days=days_forward)
    ).strftime("%Y%m%d")

    result = []

    for page in range(
        1,
        pages + 1
    ):

        try:

            response = requests.get(
                base,
                params={
                    "dataFinal": final_date,
                    "pagina": page,
                    "tamanhoPagina": 50,
                },
                headers=HEADERS,
                timeout=25
            )

            response.raise_for_status()

            payload = response.json()

            rows = (
                payload.get("data")
                or payload.get("resultado")
                or []
            )

            if not rows:
                break

            for row in rows:

                org = row.get(
                    "orgaoEntidade"
                )

                if isinstance(org, dict):
                    org = org.get(
                        "razaoSocial",
                        ""
                    )

                org = norm(
                    org
                    or row.get(
                        "nomeOrgao",
                        ""
                    )
                )

                obj = norm(
                    row.get(
                        "objetoCompra"
                    )
                    or row.get("objeto")
                    or row.get("descricao")
                    or ""
                )

                control = norm(
                    row.get(
                        "numeroControlePNCP"
                    )
                    or ""
                )

                link = norm(
                    row.get(
                        "linkSistemaOrigem"
                    )
                    or ""
                )

                if not link and control:
                    link = (
                        "https://pncp.gov.br/"
                        "app/editais/"
                        + control
                    )

                if not link:
                    link = (
                        "https://pncp.gov.br/"
                    )

                result.append(
                    {
                        "title": norm(
                            (org + " — " + obj)[:500]
                        ),
                        "url": link,
                        "description": obj,
                        "published": norm(
                            row.get(
                                "dataPublicacaoPncp",
                                ""
                            )
                        ),
                        "publisher": "PNCP",
                        "source_type": "PNCP",
                        "company_candidate": org,
                        "query": "PNCP propostas abertas",
                    }
                )

        except Exception:
            break

    return result


# ============================================================
# LEITURA DE PÁGINA
# ============================================================

def fetch_page(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=18,
            allow_redirects=True
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "svg"
            ]
        ):
            tag.decompose()

        title = norm(
            soup.title.get_text(
                " ",
                strip=True
            )
            if soup.title
            else ""
        )

        text = norm(
            soup.get_text(
                " ",
                strip=True
            )
        )

        return (
            title,
            text[:120000],
            response.url
        )

    except Exception:
        return (
            None,
            None,
            url
        )


# ============================================================
# EMPRESA
# ============================================================

def find_or_create_company(
    cursor,
    name,
    source_url
):

    if not validate_company_name(name):
        return None

    name = clean_company(name)

    row = cursor.execute(
        """
        SELECT id
        FROM companies
        WHERE lower(name)=lower(?)
        """,
        (name,)
    ).fetchone()

    if row:
        return row["id"]

    # NÃO usar domínio da notícia como website da empresa.
    # Isso evita cadastrar exame.com como website de uma empresa.
    website = ""

    # Se a URL for claramente domínio próprio,
    # pode ser usada como candidato de website.
    domain = source_domain(
        source_url
    )

    if (
        domain
        and domain not in MEDIA_DOMAINS
        and not domain.endswith(".gov.br")
        and not domain.endswith(".jus.br")
        and not domain.endswith(".leg.br")
        and not domain.endswith(".edu.br")
    ):
        website = "https://" + domain

    cursor.execute(
        """
        INSERT INTO companies(
            name,
            website,
            icp,
            created_at,
            updated_at
        )
        VALUES(?,?,?,?,?)
        """,
        (
            name,
            website,
            "UNKNOWN",
            now(),
            now()
        )
    )

    return cursor.lastrowid


# ============================================================
# ICP
# ============================================================

def infer_icp(signals):

    text = " ".join(
        norm(
            signal.get(
                "evidence",
                ""
            )
        )
        for signal in signals
    ).lower()

    # Fora do ICP direto da operação comercial.
    out_terms = [
        "prefeitura",
        "município",
        "municipio",
        "câmara municipal",
        "camara municipal",
        "secretaria municipal",
        "governo estadual",
        "ministério",
        "ministerio",
        "universidade federal",
        "instituto federal",
        "forças armadas",
        "forcas armadas",
    ]

    if any(
        term in text
        for term in out_terms
    ):
        return "OUT"

    # Evidência forte de ambiente corporativo/escala.
    clear_terms = [
        "rede de lojas",
        "novas lojas",
        "filiais",
        "unidades",
        "centro de distribuição",
        "centro de distribuicao",
        "data center",
        "operações nacionais",
        "operacoes nacionais",
        "operações em todo o brasil",
        "operacoes em todo o brasil",
        "milhares de usuários",
        "milhares de usuarios",
        "milhares de colaboradores",
        "centenas de endpoints",
        "ambiente corporativo",
    ]

    if any(
        term in text
        for term in clear_terms
    ):
        return "CLEAR"

    likely_terms = [
        "empresa de médio porte",
        "empresa de medio porte",
        "empresa de grande porte",
        "grupo empresarial",
        "holding",
        "varejista",
        "indústria",
        "industria",
        "logística",
        "logistica",
        "saúde",
        "saude",
        "construção",
        "construcao",
        "serviços financeiros",
        "servicos financeiros",
    ]

    if any(
        term in text
        for term in likely_terms
    ):
        return "LIKELY"

    return "UNKNOWN"


# ============================================================
# CLASSIFICAÇÃO HUNTER
# ============================================================

def classify_company(signals):

    signals = filter_signals(
        signals
    )

    if not signals:
        return (
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "NONE",
            "UNKNOWN",
            0,
            "LOW",
            "IGNORE"
        )

    # --------------------------------------------------------
    # Deduplicação
    # --------------------------------------------------------

    unique = {}

    for signal in signals:

        key = (
            signal.get("kind"),
            signal.get("source_id"),
            norm(
                signal.get(
                    "evidence",
                    ""
                )
            ).lower()
        )

        unique[key] = signal

    signals = list(
        unique.values()
    )

    # --------------------------------------------------------
    # Agrupamento
    # --------------------------------------------------------

    groups = {}

    for signal in signals:
        groups.setdefault(
            signal["kind"],
            []
        ).append(signal)

    # --------------------------------------------------------
    # Evidência independente por fonte
    # --------------------------------------------------------

    def source_count(kind):

        return len(
            {
                signal.get("source_id")
                for signal in signals
                if signal.get("kind") == kind
                and signal.get("source_id") is not None
            }
        )

    intent_n = source_count(
        "BUYING_INTENT"
    )

    need_n = source_count(
        "NEED_SIGNAL"
    )

    pain_n = source_count(
        "PAIN_RISK"
    )

    trigger_n = source_count(
        "BUSINESS_TRIGGER"
    )

    dm_n = source_count(
        "DECISION_MAKER"
    )

    # --------------------------------------------------------
    # Intent
    # --------------------------------------------------------

    if intent_n >= 3:
        intent = "VERY HIGH"
    elif intent_n >= 2:
        intent = "HIGH"
    elif intent_n >= 1:
        intent = "MEDIUM"
    else:
        intent = "NONE"

    # --------------------------------------------------------
    # Need
    # --------------------------------------------------------

    if need_n >= 2:
        need = "HIGH"
    elif need_n == 1:
        need = "MEDIUM"
    else:
        need = "NONE"

    # --------------------------------------------------------
    # Pain
    # --------------------------------------------------------

    if pain_n >= 2:
        pain = "HIGH"
    elif pain_n == 1:
        pain = "MEDIUM"
    else:
        pain = "NONE"

    # --------------------------------------------------------
    # Timing
    # --------------------------------------------------------

    if trigger_n >= 2:
        timing = "HIGH"
    elif trigger_n == 1:
        timing = "MEDIUM"
    else:
        timing = "NONE"

    # --------------------------------------------------------
    # Decision Maker
    # --------------------------------------------------------

    dm = (
        "LIKELY"
        if dm_n
        else "NONE"
    )

    # --------------------------------------------------------
    # ICP
    # --------------------------------------------------------

    icp = infer_icp(
        signals
    )

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    icp_points = {
        "OUT": 0,
        "UNKNOWN": 7,
        "LIKELY": 12,
        "CLEAR": 15,
    }

    score = icp_points[icp]

    score += {
        "NONE": 0,
        "MEDIUM": 6,
        "HIGH": 15,
        "VERY HIGH": 25,
    }[intent]

    score += {
        "NONE": 0,
        "MEDIUM": 10,
        "HIGH": 20,
    }[need]

    score += {
        "NONE": 0,
        "MEDIUM": 10,
        "HIGH": 20,
    }[pain]

    score += {
        "NONE": 0,
        "MEDIUM": 5,
        "HIGH": 10,
    }[timing]

    if dm == "LIKELY":
        score += 7

    score += calculate_specificity_bonus(
        signals
    )

    # --------------------------------------------------------
    # Containment V1.1
    # --------------------------------------------------------

    score = min(
        score,
        {
            "NONE": 30,
            "MEDIUM": 75,
            "HIGH": 90,
            "VERY HIGH": 100,
        }[intent]
    )

    # --------------------------------------------------------
    # ICP OUT = GATE ABSOLUTO
    # --------------------------------------------------------

    if icp == "OUT":
        return (
            intent,
            need,
            pain,
            timing,
            dm,
            icp,
            0,
            "HIGH",
            "IGNORE"
        )

    # --------------------------------------------------------
    # Trigger sozinho NÃO é oportunidade
    # --------------------------------------------------------

    commercial_evidence = (
        need != "NONE"
        or pain != "NONE"
        or intent != "NONE"
    )

    if not commercial_evidence:
        return (
            intent,
            need,
            pain,
            timing,
            dm,
            icp,
            score,
            "LOW",
            "IGNORE"
        )

    # --------------------------------------------------------
    # Classificação
    # --------------------------------------------------------

    if (
        intent == "VERY HIGH"
        and need != "NONE"
        and score >= 75
    ):
        classification = "HOT"

    elif (
        intent in ("HIGH", "VERY HIGH")
        and need != "NONE"
        and score >= 55
    ):
        classification = "WARM"

    else:
        classification = "WATCH"

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    if (
        intent in ("HIGH", "VERY HIGH")
        and need != "NONE"
    ):
        confidence = "HIGH"

    elif (
        need != "NONE"
        or pain != "NONE"
        or intent != "NONE"
    ):
        confidence = "MEDIUM"

    else:
        confidence = "LOW"

    return (
        intent,
        need,
        pain,
        timing,
        dm,
        icp,
        score,
        confidence,
        classification
    )


# ============================================================
# HUNTER
# ============================================================

def qualify_hunter(cursor):

    rows = cursor.execute(
        """
        SELECT
            c.id,
            c.name,
            c.website,
            c.icp,
            s.id AS signal_id,
            s.source_id,
            s.kind,
            s.evidence,
            s.confidence
        FROM companies c
        JOIN signals s
            ON s.company_id=c.id
        ORDER BY
            c.id,
            s.created_at DESC
        """
    ).fetchall()

    companies = {}

    for row in rows:

        company = companies.setdefault(
            row["id"],
            {
                "id": row["id"],
                "name": row["name"],
                "website": row["website"],
                "icp": row["icp"],
                "signals": [],
            }
        )

        company["signals"].append(
            dict(row)
        )

    created = 0
    updated = 0

    for company_id, company in companies.items():

        (
            intent,
            need,
            pain,
            timing,
            dm,
            icp,
            score,
            confidence,
            classification
        ) = classify_company(
            company["signals"]
        )

        cursor.execute(
            """
            UPDATE companies
            SET icp=?,
                updated_at=?
            WHERE id=?
            """,
            (
                icp,
                now(),
                company_id
            )
        )

        groups = {}

        for signal in company["signals"]:

            groups.setdefault(
                signal["kind"],
                []
            ).append(
                signal["evidence"]
            )

        trigger_text = (
            " | ".join(
                groups.get(
                    "BUSINESS_TRIGGER",
                    []
                )[:3]
            )
            or "Não identificado"
        )

        need_text = (
            " | ".join(
                groups.get(
                    "NEED_SIGNAL",
                    []
                )[:3]
            )
            or "Não confirmado"
        )

        pain_text = (
            " | ".join(
                groups.get(
                    "PAIN_RISK",
                    []
                )[:3]
            )
            or "Não confirmado"
        )

        reason = "\n".join(
            f"{kind}: {' | '.join(values[:3])}"
            for kind, values in groups.items()
            if values
        )

        actions = {
            "HOT": (
                "Abordar decisor rapidamente e "
                "validar processo de compra."
            ),
            "WARM": (
                "Abordagem consultiva e "
                "validação da necessidade."
            ),
            "WATCH": (
                "Monitorar novos sinais antes "
                "de abordagem comercial."
            ),
            "IGNORE": (
                "Não abordar; aguardar "
                "evidência adicional."
            ),
        }

        next_action = actions[
            classification
        ]

        values = (
            trigger_text,
            need_text,
            pain_text,
            intent,
            dm,
            timing,
            score,
            confidence,
            classification,
            next_action,
            reason,
            now(),
        )

        existing = cursor.execute(
            """
            SELECT id
            FROM opportunities
            WHERE company_id=?
            """,
            (company_id,)
        ).fetchone()

        if existing:

            cursor.execute(
                """
                UPDATE opportunities
                SET
                    trigger_text=?,
                    need=?,
                    pain=?,
                    intent=?,
                    dm=?,
                    timing=?,
                    score=?,
                    confidence=?,
                    classification=?,
                    next_action=?,
                    reason=?,
                    updated_at=?
                WHERE company_id=?
                """,
                values + (company_id,)
            )

            updated += 1

        else:

            cursor.execute(
                """
                INSERT INTO opportunities(
                    company_id,
                    trigger_text,
                    need,
                    pain,
                    intent,
                    dm,
                    timing,
                    score,
                    confidence,
                    classification,
                    next_action,
                    reason,
                    created_at,
                    updated_at
                )
                VALUES(
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    company_id,
                ) + values
            )

            created += 1

    return created, updated


# ============================================================
# CAÇA
# ============================================================

def run_hunt():

    con = get_db()
    cursor = con.cursor()

    cursor.execute(
        """
        INSERT INTO hunts(
            started_at,
            status
        )
        VALUES(?,?)
        """,
        (
            now(),
            "RUNNING"
        )
    )

    hunt_id = cursor.lastrowid

    con.commit()

    raw = []
    seen = set()

    sources_found = 0
    signals_found = 0
    unassigned = 0

    try:

        # ====================================================
        # MILO
        # ====================================================

        for query in SEARCH_QUERIES:

            items = rss_search(
                query
            )

            for item in items:

                key = item["url"]

                if key not in seen:

                    seen.add(key)
                    raw.append(item)

        # ====================================================
        # PNCP
        # ====================================================

        for item in pncp_search():

            key = (
                item["url"]
                + "|"
                + item["title"][:120]
            )

            if key not in seen:

                seen.add(key)
                raw.append(item)

        sources_found = len(
            raw
        )

        # ====================================================
        # GATE MILO
        # ====================================================

        all_terms = (
            INTENT_STRONG
            + INTENT_CONTEXT
            + NEED_TERMS
            + TRIGGER_TERMS
            + PAIN_TERMS
            + DM_TERMS
        )

        candidates = []

        for item in raw:

            meta = norm(
                item.get(
                    "title",
                    ""
                )
                + " "
                + item.get(
                    "description",
                    ""
                )
            )

            hits = set(
                term_hits(
                    meta,
                    all_terms
                )
            )

            if (
                hits
                or item.get(
                    "source_type"
                ) == "PNCP"
            ):

                weight = len(hits)

                if item.get(
                    "source_type"
                ) == "PNCP":
                    weight += 5

                candidates.append(
                    (
                        weight,
                        item
                    )
                )

        candidates.sort(
            key=lambda x: -x[0]
        )

        # ====================================================
        # LEITURA PROFUNDA
        # ====================================================

        for _, item in candidates[:450]:

            description = item.get(
                "description",
                ""
            )

            page_title, page_text, final_url = fetch_page(
                item.get(
                    "url",
                    ""
                )
            )

            title = (
                page_title
                or item.get(
                    "title",
                    ""
                )
            )

            body = (
                page_text
                or description
            )

            combined = norm(
                title
                + " "
                + description
                + " "
                + body
            )

            # =================================================
            # ENTITY
            # =================================================

            company = extract_company(
                title,
                body,
                item.get(
                    "publisher",
                    ""
                ),
                item.get(
                    "company_candidate"
                ),
                final_url
            )

            company_id = None

            if company:

                company_id = find_or_create_company(
                    cursor,
                    company,
                    final_url
                )

            # =================================================
            # SOURCE
            # =================================================

            cursor.execute(
                """
                INSERT INTO sources(
                    company_id,
                    title,
                    url,
                    source_type,
                    publisher,
                    collected_at,
                    content,
                    published_at,
                    query
                )
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(url)
                DO UPDATE SET
                    company_id=COALESCE(
                        excluded.company_id,
                        sources.company_id
                    ),
                    title=excluded.title,
                    publisher=excluded.publisher,
                    collected_at=excluded.collected_at,
                    content=excluded.content,
                    published_at=excluded.published_at,
                    query=excluded.query
                """,
                (
                    company_id,
                    title,
                    final_url,
                    item.get(
                        "source_type",
                        "NEWS"
                    ),
                    item.get(
                        "publisher",
                        ""
                    ),
                    now(),
                    body[:50000],
                    item.get(
                        "published",
                        ""
                    ),
                    item.get(
                        "query",
                        ""
                    ),
                )
            )

            source_row = cursor.execute(
                """
                SELECT id
                FROM sources
                WHERE url=?
                """,
                (
                    final_url,
                )
            ).fetchone()

            source_id = (
                source_row["id"]
                if source_row
                else None
            )

            # =================================================
            # INTENT
            # =================================================

            intent_terms = (
                INTENT_STRONG.copy()
            )

            generic_intent = term_hits(
                combined,
                INTENT_CONTEXT
            )

            technical_context = term_hits(
                combined,
                list(TECH_TERMS)
            )

            if (
                generic_intent
                and technical_context
            ):
                intent_terms += (
                    INTENT_CONTEXT
                )

            signal_definitions = [
                (
                    "BUYING_INTENT",
                    intent_terms
                ),
                (
                    "NEED_SIGNAL",
                    NEED_TERMS
                ),
                (
                    "BUSINESS_TRIGGER",
                    TRIGGER_TERMS
                ),
                (
                    "PAIN_RISK",
                    PAIN_TERMS
                ),
                (
                    "DECISION_MAKER",
                    DM_TERMS
                ),
            ]

            # =================================================
            # SIGNALS
            # =================================================

            for kind, terms in signal_definitions:

                snippets = evidence_snippets(
                    combined,
                    terms,
                    4
                )

                for evidence in snippets:

                    # Contratação de pessoa não é
                    # buying intent.
                    if (
                        kind == "BUYING_INTENT"
                        and is_hiring_signal(
                            evidence
                        )
                    ):
                        continue

                    # Negação explícita.
                    if has_negative_keywords(
                        evidence
                    ):
                        continue

                    # Intent precisa ser validado.
                    if (
                        kind == "BUYING_INTENT"
                        and not validate_buying_intent(
                            evidence
                        )
                    ):
                        continue

                    signal_type = classify_signal_type(
                        evidence
                    )

                    if (
                        signal_type == "NOISE"
                    ):
                        continue

                    exists = cursor.execute(
                        """
                        SELECT id
                        FROM signals
                        WHERE source_id=?
                          AND kind=?
                          AND evidence=?
                        """,
                        (
                            source_id,
                            kind,
                            evidence
                        )
                    ).fetchone()

                    if exists:
                        continue

                    confidence = "MEDIUM"

                    if (
                        item.get(
                            "source_type"
                        ) == "PNCP"
                        and kind == "BUYING_INTENT"
                    ):
                        confidence = "HIGH"

                    cursor.execute(
                        """
                        INSERT INTO signals(
                            company_id,
                            source_id,
                            kind,
                            evidence,
                            evidence_type,
                            confidence,
                            created_at
                        )
                        VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            company_id,
                            source_id,
                            kind,
                            evidence,
                            "FACT",
                            confidence,
                            now()
                        )
                    )

                    signals_found += 1

                    if company_id is None:
                        unassigned += 1

            con.commit()

        # ====================================================
        # HUNTER
        # ====================================================

        new_opportunities, updated_opportunities = qualify_hunter(
            cursor
        )

        companies_count = cursor.execute(
            """
            SELECT COUNT(*)
            FROM companies
            """
        ).fetchone()[0]

        unassigned_total = cursor.execute(
            """
            SELECT COUNT(*)
            FROM signals
            WHERE company_id IS NULL
            """
        ).fetchone()[0]

        cursor.execute(
            """
            UPDATE hunts
            SET
                finished_at=?,
                status=?,
                sources_found=?,
                signals_found=?,
                companies=?,
                new_opps=?,
                updated_opps=?,
                discarded=?,
                unassigned_signals=?
            WHERE id=?
            """,
            (
                now(),
                "COMPLETED",
                sources_found,
                signals_found,
                companies_count,
                new_opportunities,
                updated_opportunities,
                0,
                unassigned_total,
                hunt_id
            )
        )

        con.commit()

        return (
            hunt_id,
            sources_found,
            signals_found,
            companies_count,
            new_opportunities,
            updated_opportunities,
            unassigned_total,
            unassigned
        )

    except Exception:

        cursor.execute(
            """
            UPDATE hunts
            SET
                finished_at=?,
                status=?
            WHERE id=?
            """,
            (
                now(),
                "FAILED",
                hunt_id
            )
        )

        con.commit()

        raise

    finally:
        con.close()


# ============================================================
# CONSULTAS
# ============================================================

def opportunities():

    con = get_db()

    rows = con.execute(
        """
        SELECT
            o.*,
            c.name,
            c.website,
            c.icp
        FROM opportunities o
        JOIN companies c
            ON c.id=o.company_id
        ORDER BY
            o.score DESC,
            o.updated_at DESC
        """
    ).fetchall()

    con.close()

    return [
        dict(row)
        for row in rows
    ]


def all_signals():

    con = get_db()

    rows = con.execute(
        """
        SELECT
            s.*,
            c.name AS company,
            src.title,
            src.url,
            src.source_type,
            src.publisher,
            src.collected_at
        FROM signals s
        LEFT JOIN companies c
            ON c.id=s.company_id
        LEFT JOIN sources src
            ON src.id=s.source_id
        ORDER BY
            s.created_at DESC
        """
    ).fetchall()

    con.close()

    return [
        dict(row)
        for row in rows
    ]


def evidence(opportunity_id):

    con = get_db()

    rows = con.execute(
        """
        SELECT
            s.kind,
            s.evidence,
            s.confidence,
            src.title,
            src.url,
            src.collected_at,
            src.source_type
        FROM signals s
        JOIN sources src
            ON src.id=s.source_id
        JOIN opportunities o
            ON o.id=?
        WHERE s.company_id=o.company_id
        ORDER BY
            s.created_at DESC
        """,
        (
            opportunity_id,
        )
    ).fetchall()

    con.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "🔎 HUNTER TECHS"
)

st.caption(
    "Opportunity Intelligence Radar — "
    "CAÇA REAL • MILO + VALIDATOR + ENTITY + HUNTER"
)


# ============================================================
# MÉTRICAS
# ============================================================

con = get_db()

companies_count = con.execute(
    "SELECT COUNT(*) FROM companies"
).fetchone()[0]

signals_count = con.execute(
    "SELECT COUNT(*) FROM signals"
).fetchone()[0]

opportunities_count = con.execute(
    """
    SELECT COUNT(*)
    FROM opportunities
    WHERE classification!='IGNORE'
    """
).fetchone()[0]

hot_count = con.execute(
    """
    SELECT COUNT(*)
    FROM opportunities
    WHERE classification='HOT'
    """
).fetchone()[0]

warm_count = con.execute(
    """
    SELECT COUNT(*)
    FROM opportunities
    WHERE classification='WARM'
    """
).fetchone()[0]

con.close()

a, b, c, d, e = st.columns(5)

a.metric(
    "Empresas",
    companies_count
)

b.metric(
    "Sinais",
    signals_count
)

c.metric(
    "Oportunidades",
    opportunities_count
)

d.metric(
    "HOT",
    hot_count
)

e.metric(
    "WARM",
    warm_count
)


# ============================================================
# CAÇA
# ============================================================

if st.button(
    "🔎 IR PARA CAÇA",
    type="primary",
    use_container_width=True
):

    with st.spinner(
        "Milo lendo fontes públicas e Hunter validando evidências..."
    ):

        try:

            result = run_hunt()

            st.success(
                f"Caça #{result[0]} concluída — "
                f"{result[1]} fontes | "
                f"{result[2]} sinais novos | "
                f"{result[3]} empresas | "
                f"{result[4]} novas oportunidades | "
                f"{result[5]} atualizadas | "
                f"{result[6]} sinais sem empresa"
            )

        except Exception as error:

            st.error(
                f"Erro na caça: {error}"
            )


# ============================================================
# VISÕES
# ============================================================

st.divider()

view = st.radio(
    "Visão",
    [
        "Oportunidades",
        "Sinais do Milo"
    ],
    horizontal=True
)


# ============================================================
# OPORTUNIDADES
# ============================================================

if view == "Oportunidades":

    classification_filter = st.selectbox(
        "Classificação",
        [
            "TODAS",
            "HOT",
            "WARM",
            "WATCH",
            "IGNORE"
        ]
    )

    for opportunity in opportunities():

        classification = opportunity[
            "classification"
        ]

        if (
            classification_filter != "TODAS"
            and classification != classification_filter
        ):
            continue

        icon = {
            "HOT": "🔥",
            "WARM": "🟠",
            "WATCH": "👁️",
            "IGNORE": "⛔"
        }[classification]

        with st.container(
            border=True
        ):

            x, y, z = st.columns(
                [6, 1, 1]
            )

            x.subheader(
                f"{icon} {opportunity['name']}"
            )

            x.caption(
                opportunity["website"]
                or "Website não confirmado"
            )

            y.metric(
                "Score",
                opportunity["score"]
            )

            z.metric(
                "Confidence",
                opportunity["confidence"]
            )

            st.write(
                f"**ICP:** {opportunity['icp']} | "
                f"**Intent:** {opportunity['intent']} | "
                f"**Need:** {opportunity['need']} | "
                f"**Pain/Risk:** {opportunity['pain']} | "
                f"**Timing:** {opportunity['timing']} | "
                f"**DM:** {opportunity['dm']}"
            )

            st.write(
                f"**Próxima ação:** "
                f"{opportunity['next_action']}"
            )

            with st.expander(
                "Evidências rastreáveis"
            ):

                st.write(
                    opportunity["reason"]
                )

                for item in evidence(
                    opportunity["id"]
                ):

                    st.markdown(
                        f"- **{item['kind']} / "
                        f"{item['confidence']}:** "
                        f"{item['evidence']}"
                    )

                    st.caption(
                        f"{item['title']} — "
                        f"{item['url']} | "
                        f"{item['source_type']} | "
                        f"{item['collected_at']}"
                    )


# ============================================================
# SINAIS MILO
# ============================================================

else:

    signals = all_signals()

    st.caption(
        f"Milo estruturou {len(signals)} sinais. "
        "Sinais sem empresa permanecem armazenados "
        "e não viram oportunidade automaticamente."
    )

    for signal in signals[:400]:

        with st.container(
            border=True
        ):

            company = (
                signal["company"]
                or "Empresa ainda não resolvida"
            )

            x, y = st.columns(
                [6, 1]
            )

            x.markdown(
                f"**{company}** — "
                f"`{signal['kind']}`"
            )

            y.caption(
                signal["source_type"]
                or ""
            )

            st.write(
                signal["evidence"]
            )

            st.caption(
                f"{signal['title']} | "
                f"{signal['url']} | "
                f"{signal['collected_at']}"
            )


# ============================================================
# EXPORTAÇÃO
# ============================================================

st.divider()

st.subheader(
    "Exportação"
)


opportunity_rows = []

for opportunity in opportunities():

    opportunity_rows.append(
        {
            "Company": opportunity["name"],
            "Website": opportunity["website"],
            "ICP Fit": opportunity["icp"],
            "Business Trigger": opportunity["trigger_text"],
            "Need Signal": opportunity["need"],
            "Pain/Risk": opportunity["pain"],
            "Buying Intent": opportunity["intent"],
            "Decision Maker": opportunity["dm"],
            "Timing": opportunity["timing"],
            "Score": opportunity["score"],
            "Confidence": opportunity["confidence"],
            "Classification": opportunity["classification"],
            "Next Action": opportunity["next_action"],
        }
    )


opportunity_df = pd.DataFrame(
    opportunity_rows
)


st.download_button(
    "⬇️ Exportar CSV",
    opportunity_df.to_csv(
        index=False
    ).encode("utf-8-sig"),
    "hunter_techs.csv",
    "text/csv"
)


signal_rows = []

for signal in all_signals():

    signal_rows.append(
        {
            "Company": signal["company"] or "",
            "Signal Type": signal["kind"],
            "Evidence": signal["evidence"],
            "Confidence": signal["confidence"],
            "Source Type": signal["source_type"] or "",
            "Source": signal["title"] or "",
            "URL": signal["url"] or "",
        }
    )


signal_df = pd.DataFrame(
    signal_rows
)


st.download_button(
    "⬇️ Exportar sinais do Milo CSV",
    signal_df.to_csv(
        index=False
    ).encode("utf-8-sig"),
    "hunter_techs_milo_signals.csv",
    "text/csv"
)


buffer = io.BytesIO()

with pd.ExcelWriter(
    buffer,
    engine="openpyxl"
) as writer:

    opportunity_df.to_excel(
        writer,
        index=False,
        sheet_name="Opportunities"
    )

    signal_df.to_excel(
        writer,
        index=False,
        sheet_name="Milo_Signals"
    )


st.download_button(
    "⬇️ Exportar XLSX",
    buffer.getvalue(),
    "hunter_techs.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
