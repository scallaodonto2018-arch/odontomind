"""Importador da planilha ControleODONTO - Pacientes.xlsx"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from database import get_conn
from importers.utils import (
    normalizar_telefone, normalizar_cpf, normalizar_data,
    normalizar_valor, str_ou_none,
)


# Mapeamento de colunas da planilha para campos internos
_COLUNAS = {
    "Nome Completo": "nome",
    "CPF": "cpf",
    "Celulares": "whatsapp",
    "Telefones": "telefone",
    "Email": "email",
    "Data Nascimento": "data_nascimento",
    "Data do Último Atendimento": "ultima_consulta",
    "Data Cadastro": "data_cadastro",
    "Captação": "captacao",
    "BalancaFinanceira": "balanca_financeira",
    "Nº Prontuário": "prontuario_id",  # Nº Prontuário (ordinal masculino)
}


def importar(tenant_id: str, filepath: str, callback=None) -> dict:
    """
    Importa pacientes da planilha exportada pelo Controle Odonto.
    Header na linha 1 (pandas header=0).
    Retorna {"inseridos": int, "atualizados": int, "erros": int, "total": int}
    """
    df = pd.read_excel(filepath, header=0, dtype=str)

    # Renomear colunas para nomes internos
    df = df.rename(columns={k: v for k, v in _COLUNAS.items() if k in df.columns})

    inseridos = atualizados = erros = 0
    total = len(df)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                if callback:
                    callback(idx + 1, total)
                try:
                    nome = str_ou_none(row.get("nome"))
                    if not nome:
                        continue

                    prontuario = str_ou_none(row.get("prontuario_id"))
                    cpf = normalizar_cpf(row.get("cpf"))
                    whatsapp = normalizar_telefone(row.get("whatsapp"))
                    telefone = normalizar_telefone(row.get("telefone"))
                    email = str_ou_none(row.get("email"))
                    nascimento = normalizar_data(row.get("data_nascimento"))
                    ultima = normalizar_data(row.get("ultima_consulta"))
                    cadastro = normalizar_data(row.get("data_cadastro"))
                    captacao = str_ou_none(row.get("captacao"))
                    balanca = normalizar_valor(row.get("balanca_financeira"))

                    # Tenta upsert por prontuario_id
                    if prontuario:
                        cur.execute("""
                            INSERT INTO pacientes (
                                tenant_id, prontuario_id, cpf, nome,
                                whatsapp, telefone, email,
                                data_nascimento, ultima_consulta, data_cadastro,
                                captacao, balanca_financeira
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (tenant_id, prontuario_id)
                            WHERE prontuario_id IS NOT NULL
                            DO UPDATE SET
                                cpf = COALESCE(EXCLUDED.cpf, pacientes.cpf),
                                nome = EXCLUDED.nome,
                                whatsapp = COALESCE(EXCLUDED.whatsapp, pacientes.whatsapp),
                                telefone = COALESCE(EXCLUDED.telefone, pacientes.telefone),
                                email = COALESCE(EXCLUDED.email, pacientes.email),
                                data_nascimento = COALESCE(EXCLUDED.data_nascimento, pacientes.data_nascimento),
                                ultima_consulta = COALESCE(EXCLUDED.ultima_consulta, pacientes.ultima_consulta),
                                data_cadastro = COALESCE(EXCLUDED.data_cadastro, pacientes.data_cadastro),
                                captacao = COALESCE(EXCLUDED.captacao, pacientes.captacao),
                                balanca_financeira = COALESCE(EXCLUDED.balanca_financeira, pacientes.balanca_financeira),
                                atualizado_em = NOW()
                            RETURNING (xmax = 0) as eh_novo
                        """, (tenant_id, prontuario, cpf, nome,
                              whatsapp, telefone, email,
                              nascimento, ultima, cadastro,
                              captacao, balanca))
                        resultado = cur.fetchone()
                    elif cpf:
                        # Fallback: upsert por CPF
                        cur.execute("""
                            INSERT INTO pacientes (
                                tenant_id, cpf, nome,
                                whatsapp, telefone, email,
                                data_nascimento, ultima_consulta, data_cadastro,
                                captacao, balanca_financeira
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (tenant_id, cpf)
                            WHERE cpf IS NOT NULL AND cpf <> ''
                            DO UPDATE SET
                                nome = EXCLUDED.nome,
                                whatsapp = COALESCE(EXCLUDED.whatsapp, pacientes.whatsapp),
                                telefone = COALESCE(EXCLUDED.telefone, pacientes.telefone),
                                email = COALESCE(EXCLUDED.email, pacientes.email),
                                data_nascimento = COALESCE(EXCLUDED.data_nascimento, pacientes.data_nascimento),
                                ultima_consulta = COALESCE(EXCLUDED.ultima_consulta, pacientes.ultima_consulta),
                                data_cadastro = COALESCE(EXCLUDED.data_cadastro, pacientes.data_cadastro),
                                captacao = COALESCE(EXCLUDED.captacao, pacientes.captacao),
                                balanca_financeira = COALESCE(EXCLUDED.balanca_financeira, pacientes.balanca_financeira),
                                atualizado_em = NOW()
                            RETURNING (xmax = 0) as eh_novo
                        """, (tenant_id, cpf, nome,
                              whatsapp, telefone, email,
                              nascimento, ultima, cadastro,
                              captacao, balanca))
                        resultado = cur.fetchone()
                    else:
                        # Sem prontuário nem CPF: insere sem chave de deduplicação
                        cur.execute("""
                            INSERT INTO pacientes (
                                tenant_id, nome, whatsapp, telefone, email,
                                data_nascimento, ultima_consulta, data_cadastro, captacao
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            RETURNING TRUE
                        """, (tenant_id, nome, whatsapp, telefone, email,
                              nascimento, ultima, cadastro, captacao))
                        resultado = cur.fetchone()

                    if resultado and resultado[0]:
                        inseridos += 1
                    else:
                        atualizados += 1

                except Exception as e:
                    erros += 1
                    print(f"Erro na linha {idx+2}: {e}")

    return {"inseridos": inseridos, "atualizados": atualizados, "erros": erros, "total": total}
