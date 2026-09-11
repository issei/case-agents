import re
import unicodedata

# Dicionário mínimo de variantes ortográficas do domínio
DOMAIN_VARIANTS = [
    (r"\bsegunda[\s\-]+via\b", "segundavia"),
    (r"\bcartao(?:s)?[\s\-]+(?:de[\s\-]+)?credito\b", "cartaocredito"),
    (r"\bcartao(?:s)?[\s\-]+(?:de[\s\-]+)?debito\b", "cartaodebito"),
    (r"\bface[\s\-]+id\b", "faceid"),
    (r"\bchave[\s\-]+pix\b", "chavepix"),
    (r"\bcash[\s\-]+back\b", "cashback"),
    (r"\bpay[\s\-]+pal\b", "paypal"),
    (r"\bhome[\s\-]+broker\b", "homebroker"),
]


def remove_accents(text: str) -> str:
    nfkd_form = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def normalize(text: str) -> str:
    if not text:
        return ""

    # 1. Lowercase
    text = text.lower()

    # 2. Remover acentos
    text = remove_accents(text)

    # 3. Variantes ortográficas do domínio (antes de remover pontuação se houver hífens)
    for pattern, replacement in DOMAIN_VARIANTS:
        text = re.sub(pattern, replacement, text)

    # 4. Remover caracteres especiais (manter apenas letras, números e espaços)
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # 5. Colapsar múltiplos espaços
    text = re.sub(r"\s+", " ", text).strip()

    return text
