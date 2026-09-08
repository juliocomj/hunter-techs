"""
PHASE 1: Entity Resolution & Deduplication
- NER with spaCy for company extraction
- Fuzzy matching for name variations
- Domain clustering
- Manual review queue
"""

import re
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse

try:
    import spacy
    nlp = spacy.load("pt_core_news_sm")
    HAS_SPACY = True
except:
    print("⚠️  spaCy not loaded. Install: python -m spacy download pt_core_news_sm")
    HAS_SPACY = False

try:
    from fuzzywuzzy import fuzz
    HAS_FUZZY = True
except:
    print("⚠️  fuzzywuzzy not installed")
    HAS_FUZZY = False


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


def norm(x: str) -> str:
    """Normalize whitespace."""
    return re.sub(r"\s+", " ", (x or "")).strip()


def source_domain(url: str) -> str:
    """Extract and normalize domain from URL."""
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


def extract_orgs_spacy(text: str) -> List[str]:
    """
    Extract organization names using spaCy NER.
    Returns list of organization entities.
    """
    if not HAS_SPACY or not text:
        return []
    
    try:
        doc = nlp(text[:5000])  # Limit to first 5000 chars for speed
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
        return list(set(orgs))  # Deduplicate
    except Exception as e:
        print(f"⚠️  spaCy extraction error: {e}")
        return []


def fuzzy_match(name1: str, name2: str, threshold: int = 85) -> bool:
    """
    Check if two company names are similar using fuzzy matching.
    Returns True if similarity >= threshold.
    """
    if not HAS_FUZZY:
        return name1.lower() == name2.lower()
    
    try:
        ratio = fuzz.token_set_ratio(name1.lower(), name2.lower())
        return ratio >= threshold
    except Exception:
        return name1.lower() == name2.lower()


def validate_company_name(name: str) -> bool:
    """
    Improved validation: reject generic/media names.
    Returns True if name is valid for a real company.
    """
    if not name:
        return False
    
    n = norm(name).strip(" -–—:,.()[]\"'")
    low = n.lower()
    
    # Reject media names
    if low in MEDIA_NAMES or any(low.startswith(x + " ") for x in MEDIA_NAMES):
        return False
    
    # Length checks
    if len(n) < 3 or len(n) > 110 or len(n.split()) > 10:
        return False
    
    # Reject pure numbers
    if re.fullmatch(r"[0-9 .,%/-]+", n):
        return False
    
    # Reject generic placeholders
    bad = {
        'empresa', 'companhia', 'grupo', 'organização', 'organizacao',
        'a empresa', 'a companhia', 'some company', 'uma empresa'
    }
    if low in bad:
        return False
    
    return True


def clean_company(c: str) -> str:
    """Clean and normalize company name."""
    c = norm(c).strip(" -–—:,.()[]\"'")
    
    # Prevent "Empresa X A Empresa Y" → take only first part
    m = re.search(r"\s+[AaOo]\s+(?:Empresa|Grupo|Companhia|Holding)\b", c)
    if m:
        c = c[:m.start()]
    
    # Remove generic prefixes
    c = re.sub(r"^(?:a|o|as|os|da|do|na|no)\s+", "", c, flags=re.I)
    
    # Remove verbal suffixes
    c = re.sub(
        r"\s+(?:anuncia|anunciou|contrata|contratou|busca|buscou|expande|expandiu|abre|abriu|projeta|prevê|preve|investe|investiu|vai|inicia|iniciou).*$",
        "",
        c,
        flags=re.I
    )
    
    return c.strip(" -–—:,.()[]\"'")


class EntityResolver:
    """High-level entity resolution with multiple strategies."""
    
    def __init__(self, existing_companies: List[Dict] = None):
        self.existing_companies = existing_companies or []
        self.domain_index = self._build_domain_index()
    
    def _build_domain_index(self) -> Dict[str, str]:
        """Build reverse index: domain → canonical company name."""
        index = {}
        for company in self.existing_companies:
            domain = source_domain(company.get('website', ''))
            if domain and domain not in MEDIA_DOMAINS:
                index[domain] = company['name']
        return index
    
    def resolve_company(
        self,
        title: str,
        body: str,
        publisher: str = "",
        url: str = "",
        explicit_candidate: str = None,
    ) -> Optional[str]:
        """
        Resolve company from article using multiple strategies.
        Returns canonical company name or None.
        """
        
        # Strategy 0: Explicit candidate (highest priority)
        if explicit_candidate and validate_company_name(explicit_candidate):
            return clean_company(explicit_candidate)
        
        # Strategy 1: spaCy NER extraction
        combined_text = norm(title + " " + body[:3000])
        spacy_orgs = extract_orgs_spacy(combined_text)
        
        # Filter and validate spaCy results
        valid_spacy = [org for org in spacy_orgs if validate_company_name(org)]
        
        # Strategy 2: Domain-based (if URL matches domain index)
        domain = source_domain(url)
        if domain in self.domain_index:
            canonical = self.domain_index[domain]
            if validate_company_name(canonical):
                return canonical
        
        # Strategy 3: Return best spaCy result
        if valid_spacy:
            # Prefer longer names (usually more specific)
            best = max(valid_spacy, key=len)
            return clean_company(best)
        
        # Strategy 4: Fall back to regex (existing logic, simplified)
        t = norm(title)
        verb = r"(?:anuncia|anunciou|contrata|contratou|busca|buscou|expande|expandiu|abre|abriu|projeta|prevê|preve|investe|investiu|inicia|iniciou|adota|adotou|lança|lancou|lançou|moderniza|modernizou)"
        
        for m in re.finditer(rf"^(.{{3,100}}?)\s+{verb}\b", t, flags=re.I):
            candidate = m.group(1)
            if validate_company_name(candidate):
                return clean_company(candidate)
        
        # No company found
        return None
    
    def find_duplicate(self, name: str) -> Optional[str]:
        """
        Check if a similar company already exists.
        Returns existing company name or None.
        """
        if not validate_company_name(name):
            return None
        
        clean_name = clean_company(name)
        
        for existing in self.existing_companies:
            existing_clean = clean_company(existing['name'])
            if fuzzy_match(clean_name, existing_clean, threshold=85):
                return existing['name']
        
        return None


def identify_uncertain_entities(signals_by_company: Dict) -> List[Dict]:
    """
    Identify companies with multiple signals but unvalidated entity resolution.
    Returns list of uncertain companies for manual review.
    """
    uncertain = []
    
    for company_id, company_info in signals_by_company.items():
        name = company_info.get('name', '')
        signal_count = len(company_info.get('signals', []))
        website = company_info.get('website', '')
        
        # Criteria for "uncertain":
        is_generic = any(generic in name.lower() for generic in [
            'empresa', 'companhia', 'grupo', 'start', 'tech', 'software'
        ])
        
        if signal_count >= 3 and (not website or is_generic):
            evidence_samples = [s.get('evidence', '')[:100] for s in company_info['signals'][:3]]
            
            uncertain.append({
                'company_id': company_id,
                'name': name,
                'website': website,
                'signal_count': signal_count,
                'evidence_samples': evidence_samples,
                'needs_review': True,
                'priority': 'HIGH' if signal_count >= 5 else 'MEDIUM',
            })
    
    uncertain.sort(key=lambda x: (-int(x['priority'] == 'HIGH'), -x['signal_count']))
    
    return uncertain
