"""Importador da planilha Contratos.xlsx"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from database import get_conn
from importers.utils import (
    normalizar_telefone, normalizar_data, normalizar_valor, str_ou_none,
)


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
    Importa contratos.
    Header na linha 3 (pandas header=2).
    Colunas: Contrato, Emissão, Conclusão, Dentista, Nome do Paciente,
             Telefones, Especies, Situações dos Títulos, Total, Total Clinico,
             Total Orto, Total Manutenção, Desconto Adicional,
             Campanha de Marketing, Situação, Vendedor
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
                    # ID do contrato (primeira coluna)
                    co_contrato_id = str_ou_none(row.get("Contrato"))

                    nome_paciente = str_ou_none(row.get("Nome do Paciente"))
                    telefones_raw = str_ou_none(row.get("Telefones"))
                    telefone = normalizar_telefone(telefones_raw)

                    # Data de emissão = data de assinatura do contrato
                    data_emissao = normalizar_data(row.get("Emissão") or row.get("Emissao") or row.get("Emiss?o"))
                    data_conclusao = normalizar_data(row.get("Conclusão") or row.get("Conclusao") or row.get("Conclus?o"))

                    valor_total = normalizar_valor(row.get("Total"))
                    valor_clinico = normalizar_valor(row.get("Total Clinico"))
                    valor_orto = normalizar_valor(row.get("Total Orto"))
                    valor_manut = normalizar_valor(row.get("Total Manutenção") or row.get("Total Manuten??o"))
                    desconto = normalizar_valor(row.get("Desconto Adicional"))

                    # Espécies = formas de pagamento (sem acento no arquivo)
                    forma_pgto = str_ou_none(row.get("Especies"))
                    situacao_titulos = str_ou_none(row.get("Situações dos Títulos") or row.get("Situa??es dos T?tulos"))
                    campanha = str_ou_none(row.get("Campanha de Marketing"))
                    situacao = str_ou_none(row.get("Situação") or row.get("Situa??o"))
                    vendedor = str_ou_none(row.get("Vendedor"))
                    dentista = str_ou_none(row.get("Dentista"))

                    paciente_id = _encontrar_paciente(cur, tenant_id, nome_paciente, telefone)
                    if not paciente_id:
                        sem_paciente += 1

                    if co_contrato_id:
                        cur.execute("""
                            INSERT INTO tratamentos (
                                tenant_id, paciente_id, co_contrato_id, tipo,
                                dentista, vendedor, campanha_marketing,
                                valor_total, valor_clinico, valor_orto, valor_manutencao, desconto,
                                forma_pagamento, situacao_titulos,
                                data_emissao, data_aprovacao, data_conclusao, situacao
                            ) VALUES (%s,%s,%s,'contrato',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (tenant_id, co_contrato_id)
                            WHERE co_contrato_id IS NOT NULL
                            DO UPDATE SET
                                paciente_id = COALESCE(EXCLUDED.paciente_id, tratamentos.paciente_id),
                                dentista = COALESCE(EXCLUDED.dentista, tratamentos.dentista),
                                vendedor = COALESCE(EXCLUDED.vendedor, tratamentos.vendedor),
                                campanha_marketing = COALESCE(EXCLUDED.campanha_marketing, tratamentos.campanha_marketing),
                                valor_total = COALESCE(EXCLUDED.valor_total, tratamentos.valor_total),
                                valor_clinico = COALESCE(EXCLUDED.valor_clinico, tratamentos.valor_clinico),
                                valor_orto = COALESCE(EXCLUDED.valor_orto, tratamentos.valor_orto),
                                valor_manutencao = COALESCE(EXCLUDED.valor_manutencao, tratamentos.valor_manutencao),
                                desconto = COALESCE(EXCLUDED.desconto, tratamentos.desconto),
                                forma_pagamento = COALESCE(EXCLUDED.forma_pagamento, tratamentos.forma_pagamento),
                                situacao_titulos = COALESCE(EXCLUDED.situacao_titulos, tratamentos.situacao_titulos),
                                data_emissao = COALESCE(EXCLUDED.data_emissao, tratamentos.data_emissao),
                                data_aprovacao = COALESCE(EXCLUDED.data_aprovacao, tratamentos.data_aprovacao),
                                data_conclusao = COALESCE(EXCLUDED.data_conclusao, tratamentos.data_conclusao),
                                situacao = EXCLUDED.situacao,
                                atualizado_em = NOW()
                            RETURNING (xmax = 0) as eh_novo
                        """, (tenant_id, paciente_id, co_contrato_id,
                              dentista, vendedor, campanha,
                              valor_total, valor_clinico, valor_orto, valor_manut, desconto,
                              forma_pgto, situacao_titulos,
                              data_emissao, data_emissao, data_conclusao, situacao))
                        resultado = cur.fetchone()
                    else:
                        cur.execute("""
                            INSERT INTO tratamentos (
                                tenant_id, paciente_id, tipo,
                                dentista, vendedor, campanha_marketing,
                                valor_total, valor_clinico, desconto,
                                data_emissao, data_aprovacao, situacao
                            ) VALUES (%s,%s,'contrato',%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            RETURNING TRUE
                        """, (tenant_id, paciente_id,
                              dentista, vendedor, campanha,
                              valor_total, valor_clinico, desconto,
                              data_emissao, data_emissao, situacao))
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
