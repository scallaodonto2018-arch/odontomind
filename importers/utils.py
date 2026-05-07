"""Funções de normalização de dados — padrão Brasil."""
import re
from datetime import date, datetime
from typing import Optional


def normalizar_telefone(raw) -> Optional[str]:
    """Remove não-dígitos. Retorna string de 10-11 dígitos ou None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "None", "nan", "NaT"):
        return None
    # Pega o primeiro número se houver múltiplos separados por vírgula/ponto-e-vírgula
    s = re.split(r"[;,/]", s)[0].strip()
    digits = re.sub(r"\D", "", s)
    if digits.startswith("0"):
        digits = digits[1:]
    # Remove DDI Brasil se presente
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    if len(digits) < 8 or len(digits) > 11:
        return None
    return digits


def normalizar_cpf(raw) -> Optional[str]:
    """Remove pontuação do CPF. Retorna 11 dígitos ou None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "None", "nan"):
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) != 11:
        return None
    return digits


def normalizar_valor(raw) -> Optional[float]:
    """Converte 'R$ 1.760,00' ou '1760.00' para float."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "None", "nan", "NaT"):
        return None
    # Remove símbolo de moeda e espaços
    s = re.sub(r"[R$\s]", "", s)
    # Formato BR: ponto = milhar, vírgula = decimal
    if "," in s and "." in s:
        # Ex: 1.760,00 → remover ponto, trocar vírgula por ponto
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        # Ex: 1760,00 → trocar vírgula por ponto
        s = s.replace(",", ".")
    # Else: já está no formato 1760.00
    try:
        return float(s)
    except ValueError:
        return None


def normalizar_data(raw) -> Optional[date]:
    """Aceita date, datetime, 'dd/mm/yyyy', 'yyyy-mm-dd' e variantes."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if s in ("", "None", "nan", "NaT"):
        return None
    # Remove hora se houver
    s = s.split(" ")[0].split("T")[0]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def str_ou_none(raw) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s not in ("", "None", "nan", "NaT") else None


def primeiro_nao_nulo(*valores):
    for v in valores:
        if v is not None:
            return v
    return None
