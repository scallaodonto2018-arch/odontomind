"""Importador da planilha ControleODONTO - Procedimentos Realizados.xlsx"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from database import get_conn, buscar_paciente_por_prontuario, buscar_tratamento_por_co_id
from importers.utils import (
    normalizar_telefone, normalizar_data, normalizar_valor, str_ou_none,
)


def importar(tenant_id: str, filepath: str, callback=None) -> dict:
    """
    Importa procedimentos realizados.
    Header na linha 3 (pandas header=2).
    Colunas: Data, Dentista, Nome do Paciente, Prontuário, Contato Paciente,
             Especialidade, Nome do Procedimento, Contrato, Convênio,
             Valor, Dente, Face, Situação, Observações
    """
    df = pd.read_excel(filepath, header=2, dtype=str)

    inseridos = erros = sem_paciente = 0
    total = len(df)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                if callback:
                    callback(idx + 1, total)
                try:
                    prontuario = str_ou_none(row.get("Prontuário") or row.get("Prontuario") or row.get("N° Prontuário"))
                    nome_paciente = str_ou_none(row.get("Nome do Paciente") or row.get("Paciente"))
                    co_contrato_id = str_ou_none(row.get("Contrato"))

                    data_realizacao = normalizar_data(row.get("Data"))
                    dentista = str_ou_none(row.get("Dentista"))
                    especialidade = str_ou_none(row.get("Especialidade"))
                    nome_proc = str_ou_none(row.get("Nome do Procedimento") or row.get("Procedimento"))
                    valor = normalizar_valor(row.get("Valor"))
                    dente = str_ou_none(row.get("Dente"))
                    face = str_ou_none(row.get("Face"))
                    situacao = str_ou_none(row.get("Situação") or row.get("Situacao")) or "Concluído"
                    obs = str_ou_none(row.get("Observações") or row.get("Observacoes"))

                    if not data_realizacao and not nome_proc:
                        continue

                    # Localiza paciente pelo prontuário
                    paciente_id = None
                    if prontuario:
                        paciente_id = buscar_paciente_por_prontuario(conn, tenant_id, prontuario)

                    if not paciente_id and nome_paciente:
                        # Fallback por nome
                        partes = nome_paciente.strip().split()[:3]
                        like = " ".join(partes) + "%"
                        cur.execute(
                            "SELECT id FROM pacientes WHERE tenant_id=%s AND nome ILIKE %s LIMIT 1",
                            (tenant_id, like),
                        )
                        r = cur.fetchone()
                        if r:
                            paciente_id = r[0]

                    if not paciente_id:
                        sem_paciente += 1

                    # Localiza tratamento pelo co_contrato_id
                    tratamento_id = None
                    if co_contrato_id:
                        tratamento_id = buscar_tratamento_por_co_id(conn, tenant_id, co_contrato_id, "co_contrato_id")

                    cur.execute("""
                        INSERT INTO procedimentos (
                            tenant_id, paciente_id, tratamento_id,
                            data_realizacao, dentista, especialidade,
                            nome_procedimento, valor, dente, face, situacao, observacoes
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (tenant_id, paciente_id, tratamento_id,
                          data_realizacao, dentista, especialidade,
                          nome_proc, valor, dente, face, situacao, obs))
                    inseridos += 1

                except Exception as e:
                    erros += 1
                    print(f"Erro na linha {idx+2}: {e}")

    return {"inseridos": inseridos, "erros": erros, "sem_paciente": sem_paciente, "total": total}
