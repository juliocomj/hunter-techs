"""
PHASE 1: Signal Validation
- Filter hiring signals (not buying intent)
- Negative keyword filtering
- Context-aware intent classification
"""

import re
from typing import List, Dict, Tuple


NEGATIVE_KEYWORDS = [
    # Hiring/recruitment
    'vaga', 'job posting', 'recrutamento', 'contratamos', 'procuramos profissional',
    'curriculum', 'salário', 'benefício', 'estamos contratando', 'we are hiring',
    'posição aberta', 'open position', 'hiring', 'vaga aberta',
    
    # General vendor (not tech)
    'fornecedor de papel', 'limpeza', 'café', 'escritório', 'móvel',
    
    # Content (not buying)
    'opinião', 'artigo', 'tutorial', 'como fazer', 'blog', 'guia',
    'comparação de produtos', 'resenha', 'análise de', 'review',
    
    # Bad reviews
    'não recomendo', 'decepcionante', 'ruim', 'péssimo',
]

HIRING_KEYWORDS = [
    'vaga', 'job posting', 'recrutamento', 'contratamos', 'procuramos profissional',
    'estamos contratando', 'we are hiring', 'posição aberta', 'open position',
    'curriculum', 'salário', 'benefício', 'hiring',
]

URGENT_PATTERNS = [
    r'(?:expira|vence|fim do prazo).*?(\d+\s*(?:dias|semanas|meses|horas))',
    r'(?:emergência|urgente|imediato|asap)',
    r'(?:decisão em|prazo para|deadline)',
]

MEDIUM_PATTERNS = [
    r'(?:planejamos|está marcado para|previsão).*?(Q[1-4]|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)',
    r'(?:próximos? \d+ (?:meses|semanas))',
]


def has_negative_keywords(text: str) -> bool:
    """Check if text contains hiring/non-buying keywords."""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in NEGATIVE_KEYWORDS)


def is_hiring_signal(text: str) -> bool:
    """Detect if signal is about hiring (not buying intent)."""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in HIRING_KEYWORDS)


def extract_timeline(text: str) -> Dict[str, any]:
    """Extract buying timeline from text."""
    if not text:
        return {'urgency': 'LOW', 'timeframe': None, 'confidence': 'LOW'}
    
    low = text.lower()
    
    # Check urgent patterns
    for pattern in URGENT_PATTERNS:
        if re.search(pattern, low, re.I):
            match = re.search(pattern, low, re.I)
            timeframe = match.group(1) if match.lastindex else 'urgent'
            return {'urgency': 'URGENT', 'timeframe': timeframe, 'confidence': 'HIGH'}
    
    # Check medium patterns
    for pattern in MEDIUM_PATTERNS:
        if re.search(pattern, low, re.I):
            match = re.search(pattern, low, re.I)
            timeframe = match.group(1) if match.lastindex else 'q-next'
            return {'urgency': 'MEDIUM', 'timeframe': timeframe, 'confidence': 'HIGH'}
    
    return {'urgency': 'LOW', 'timeframe': None, 'confidence': 'LOW'}


def extract_specificity_signals(text: str) -> Dict[str, list]:
    """Extract geographic, vertical, and size signals."""
    if not text:
        return {'geography': [], 'vertical': [], 'size': []}
    
    low = text.lower()
    result = {'geography': [], 'vertical': [], 'size': []}
    
    # Geographic signals
    geographic = {
        'São Paulo': ['são paulo', 'sp', 's.p.', 'capital'],
        'Rio de Janeiro': ['rio de janeiro', 'rj', 'r.j.'],
        'Brasília': ['brasília', 'brasilia', 'bsb'],
        'Belo Horizonte': ['belo horizonte', 'bh', 'b.h.'],
    }
    
    for city, patterns in geographic.items():
        if any(p in low for p in patterns):
            result['geography'].append(city)
    
    # Vertical signals
    verticals = {
        'Financeiro': ['banco', 'financial', 'fintech', 'pagamento', 'seguros'],
        'Healthcare': ['hospital', 'clínica', 'farmacêutica', 'healthcare', 'médico'],
        'Retail': ['varejo', 'loja', 'ecommerce', 'retail', 'marketplace'],
        'Manufatura': ['indústria', 'manufatura', 'produção', 'factory'],
        'Governo': ['governo', 'prefeitura', 'secretaria', 'público', 'public'],
    }
    
    for vertical, patterns in verticals.items():
        if any(p in low for p in patterns):
            result['vertical'].append(vertical)
    
    # Size signals
    size_indicators = {
        '<100': ['startup', 'pequena empresa', 'pme', 'small'],
        '100-500': ['mid-market', 'média empresa', 'médio', 'mid-size'],
        '500-5000': ['grande empresa', 'large company', 'enterprise'],
        '>5000': ['corporação', 'multinacional', 'group', 'conglomerate'],
    }
    
    for size, patterns in size_indicators.items():
        if any(p in low for p in patterns):
            result['size'].append(size)
    
    return result


def validate_buying_intent(signals: List[Dict]) -> Tuple[bool, str]:
    """Validate if signals genuinely indicate buying intent."""
    
    if not signals:
        return False, "No signals present"
    
    # Check for hiring signals
    for sig in signals:
        if is_hiring_signal(sig.get('evidence', '')):
            return False, "Signal contains hiring keywords (not buying intent)"
    
    # Count signal types
    buying_sigs = [s for s in signals if s.get('kind') == 'BUYING_INTENT']
    need_sigs = [s for s in signals if s.get('kind') == 'NEED_SIGNAL']
    pain_sigs = [s for s in signals if s.get('kind') == 'PAIN_RISK']
    
    # Rule 1: Must have specific need or pain
    if not need_sigs and not pain_sigs:
        return False, "No NEED or PAIN signals detected"
    
    # Rule 2: Must have buying intent or strong pain
    if not buying_sigs and len(pain_sigs) < 2:
        return False, "Insufficient buying intent"
    
    # Rule 3: If only one buying signal, need pain + need
    if len(buying_sigs) == 1 and not pain_sigs:
        return False, "Single buying signal requires pain evidence"
    
    return True, "Valid buying intent combination"


def classify_signal_type(evidence: str, kind: str) -> Dict[str, any]:
    """Enhanced signal classification with context."""
    
    if not evidence:
        return {
            'kind': 'INVALID',
            'is_valid': False,
            'confidence': 'LOW',
            'notes': 'Empty evidence',
        }
    
    # Check if it's actually hiring
    if kind == 'BUYING_INTENT' and is_hiring_signal(evidence):
        return {
            'kind': 'HIRING_SIGNAL',
            'is_valid': False,
            'confidence': 'HIGH',
            'notes': 'Hiring signal, not buying intent',
        }
    
    # Check negative keywords
    if has_negative_keywords(evidence):
        return {
            'kind': 'INVALID',
            'is_valid': False,
            'confidence': 'MEDIUM',
            'notes': 'Contains negative keywords',
        }
    
    # Extract enrichment data
    timeline = extract_timeline(evidence)
    specificity = extract_specificity_signals(evidence)
    
    # Calculate confidence boost from specificity
    specificity_score = len(specificity['geography']) + len(specificity['vertical']) + len(specificity['size'])
    confidence_boost = min(specificity_score * 0.1, 0.3)
    
    base_confidence = {
        'BUYING_INTENT': 0.7,
        'NEED_SIGNAL': 0.6,
        'PAIN_RISK': 0.75,
        'BUSINESS_TRIGGER': 0.5,
        'DECISION_MAKER': 0.8,
    }.get(kind, 0.5)
    
    final_confidence = min(base_confidence + confidence_boost, 1.0)
    confidence_label = 'HIGH' if final_confidence >= 0.75 else ('MEDIUM' if final_confidence >= 0.55 else 'LOW')
    
    return {
        'kind': kind,
        'is_valid': True,
        'confidence': confidence_label,
        'confidence_score': final_confidence,
        'timeline': timeline,
        'specificity': specificity,
        'specificity_boost': specificity_score,
        'notes': f"Timeline: {timeline['urgency']}, Specificity: {specificity_score}",
    }


def filter_signals(signals: List[Dict]) -> List[Dict]:
    """Filter and validate all signals."""
    valid_signals = []
    
    for sig in signals:
        classified = classify_signal_type(sig.get('evidence', ''), sig.get('kind', ''))
        
        if not classified['is_valid']:
            continue
        
        if classified['kind'] == 'HIRING_SIGNAL':
            continue
        
        sig['validated'] = True
        sig['confidence'] = classified['confidence']
        sig['timeline'] = classified['timeline']
        sig['specificity'] = classified['specificity']
        
        valid_signals.append(sig)
    
    return valid_signals


def calculate_specificity_bonus(signals: List[Dict]) -> int:
    """Calculate bonus points for signal specificity."""
    bonus = 0
    
    for sig in signals:
        specificity = sig.get('specificity', {})
        
        if specificity.get('geography'):
            bonus += 10
        if specificity.get('vertical'):
            bonus += 10
        if specificity.get('size'):
            bonus += 5
    
    return min(bonus, 30)
