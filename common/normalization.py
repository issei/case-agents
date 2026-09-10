"""Função canônica de normalização textual do domínio bancário.

Regra invariante: Documentos indexados em fit() e queries em search() devem
obrigatoriamente passar por esta mesma função antes da vetorização.
"""
import re
import unicodedata


def normalize(text: str) -> str:
    """Normaliza o texto eliminando variações ortográficas e diacríticas.

    1. Decomposição Unicode NFKD (separa caracteres base de diacríticos)
    2. Remoção de marcas combinantes (acentos)
    3. Conversão para minúsculas
    4. Substituição de pontuação e símbolos por espaço
    5. Colapso de múltiplos espaços e strip
    """
    if not text:
        return ""
    # 1. Unicode NFKD: separa caracteres base de diacríticos
    text = unicodedata.normalize("NFKD", text)
    # 2. Remove marcas combinantes (acentos)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # 3. Converte para minúsculas
    text = text.lower()
    # 4. Substitui pontuação e símbolos por espaço
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # 5. Colapsa espaços múltiplos
    text = re.sub(r"\s+", " ", text).strip()
    return text
