"""Importador da planilha Orçamentos Emitidos.xlsx"""
import sys, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from database import get_conn
from importers.utils import (
    normalizar_telefone, normalizar_data, normalizar_valor, str_ou_none,
)


def _gerar_co_id(data_emissao, nome, valor) -> str:
    """
    Orçamentos não têm ID explícito na planilha.
    Gera hash MD5 de data+nome+valor como chave de deduplicação.
    """
    raw = f"{data_emissao}_{(nome or '').strip().lower()}_{valor or 0}"
    return "orc_" + hashlib.md5(raw.encode()).hexdigest()[:16]


def _encontrar_paciente(cur, tenant_id: str, nome: str, telefone: str) -> int | None:
    if telefone:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND (whatsapp=%s OR telefone=%s) LIMIT 1",
            (tenant_id, telefone, telefone),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    if nome:
        partes = nome.strip().split()[:3]
        like = " ".join(partes) + "%"
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND nome ILIKE %s LIMIT 1",
            (tenant_id, like),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    return None


def importar(tenant_id: str, filepath: str, callback=None) -> dict:
    """
    Importa orçamentos.
    Header na linha 3 (pandas header=2).
    Colunas: Emissão, Aprovação, Cancelado, Dentista, Nome do Paciente,
             Total Proced/Clínicos, Total Proced/Orto, Total Manutenções,
             Total Líquido, Desconto ADICIONAL, Campanha de Marketing,
             Situação, Telefones
    """
    df = pd.read_excel(filepath, header=2, dtype=str)

    inseridos = atualizados = erros = sem_paciente = 0
    total = len(df)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                if callback:
                    callback(idx + 1, total)
                try:
                    nome_paciente = str_ou_none(row.get("Nome do Paciente"))
                    telefones_raw = str_ou_none(row.get("Telefones"))
                    telefone = normalizar_telefone(telefones_raw)

                    data_emissao = normalizar_data(row.get("Emissão") or row.get("Emissao") or row.get("Emiss?o"))
                    data_aprovacao = normalizar_data(row.get("Aprovação") or row.get("Aprovacao") or row.get("Aprova??o"))
                    data_cancelado = normalizar_data(row.get("Cancelado"))

                    valor_total = normalizar_valor(row.get("Total Líquido") or row.get("Total Liquido") or row.get("Total L?quido"))
                    valor_clinico = normalizar_valor(row.get("Total Proced/Clínicos") or row.get("Total Proced/Cl?nicos"))
                    valor_orto = normalizar_valor(row.get("Total Proced/Orto"))
                    valor_manut = normalizar_valor(row.get("Total Manutenções") or row.get("Total Manuten??es") or row.get("Total Manutenções"))
                    desconto = normalizar_valor(row.get("Desconto ADICIONAL"))
                    dentista = str_ou_none(row.get("Dentista"))
                    campanha = str_ou_none(row.get("Campanha de Marketing"))
                    situacao = str_ou_none(row.get("Situação") or row.get("Situa??o"))

                    # Gera ID sintético para deduplicação
                    co_orc_id = _gerar_co_id(data_emissao, nome_paciente, valor_total)

                    if data_cancelado:
                        situacao_final = "cancelado"
                    elif data_aprovacao:
                        situacao_final = "aprovado"
                    else:
                        situacao_final = situacao or "emitido"

                    paciente_id = _encontrar_paciente(cur, tenant_id, nome_paciente, telefone)
                    if not paciente_id:
                        sem_paciente += 1

                    cur.execute("""
                        INSERT INTO tratamentos (
                            tenant_id, paciente_id, co_orcamento_id, tipo,
                            dentista, campanha_marketing,
                            valor_total, valor_clinico, valor_orto, valor_manutencao, desconto,
                            data_emissao, data_aprovacao, situacao
                        ) VALUES (%s,%s,%s,'orcamento',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (tenant_id, co_orcamento_id)
                        WHERE co_orcamento_id IS NOT NULL
                        DO UPDATE SET
                            paciente_id = COALESCE(EXCLUDED.paciente_id, tratamentos.paciente_id),
                            dentista = COALESCE(EXCLUDED.dentista, tratamentos.dentista),
                            campanha_marketing = COALESCE(EXCLUDED.campanha_marketing, tratamentos.campanha_marketing),
                            valor_total = COALESCE(EXCLUDED.valor_total, tratamentos.valor_total),
                            valor_clinico = COALESCE(EXCLUDED.valor_clinico, tratamentos.valor_clinico),
                            valor_orto = COALESCE(EXCLUDED.valor_orto, tratamentos.valor_orto),
                            valor_manutencao = COALESCE(EXCLUDED.valor_manutencao, tratamentos.valor_manutencao),
                            desconto = COALESCE(EXCLUDED.desconto, tratamentos.desconto),
                            data_emissao = COALESCE(EXCLUDED.data_emissao, tratamentos.data_emissao),
                            data_aprovacao = COALESCE(EXCLUDED.data_aprovacao, tratamentos.data_aprovacao),
                            situacao = EXCLUDED.situacao,
                            atualizado_em = NOW()
                        RETURNING (xmax = 0) as eh_novo
                    """, (tenant_id, paciente_id, co_orc_id,
                          dentista, campanha,
                          valor_total, valor_clinico, valor_orto, valor_manut, desconto,
                          data_emissao, data_aprovacao, situacao_final))

                    resultado = cur.fetchone()
                    if resultado and resultado[0]:
                        inseridos += 1
                    else:
                        atualizados += 1

                except Exception as e:
                    erros += 1
                    print(f"Erro na linha {idx+2}: {e}")

    return {
        "inseridos": inseridos, "atualizados": atualizados,
        "erros": erros, "sem_paciente": sem_paciente, "total": total,
    }
