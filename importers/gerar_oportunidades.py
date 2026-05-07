"""
Gera oportunidades históricas a partir dos tratamentos importados.

Regras:
  contrato qualquer situação  → fechado_ganho
  orçamento aprovado          → fechado_ganho
  orçamento cancelado         → fechado_perdido
  orçamento aguardando/emitido → orcamento_enviado
  demais                       → negociando
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from database import get_conn


def gerar(tenant_id: str, callback=None) -> dict:
    """
    Cria oportunidades para tratamentos que ainda não têm oportunidade vinculada.
    Idempotente: re-rodar não cria duplicatas.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.id, t.paciente_id, t.tipo, t.situacao,
                       t.valor_total, t.data_emissao, t.data_aprovacao,
                       t.vendedor, t.campanha_marketing
                FROM tratamentos t
                WHERE t.tenant_id = %s
                  AND t.paciente_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM oportunidades o
                      WHERE o.tratamento_id = t.id
                        AND o.tenant_id = %s
                  )
            """, (tenant_id, tenant_id))
            tratamentos = cur.fetchall()

            criadas = 0
            total = len(tratamentos)

            for idx, row in enumerate(tratamentos):
                if callback:
                    callback(idx + 1, total)

                tid, paciente_id, tipo, situacao, valor, d_em, d_ap, vendedor, campanha = row
                sit = (situacao or "").lower()

                if tipo == "contrato":
                    status = "fechado_ganho"
                    valor_fechado = valor
                elif "aprovado" in sit or "concluído" in sit or "conclu" in sit:
                    status = "fechado_ganho"
                    valor_fechado = valor
                elif "cancelado" in sit:
                    status = "fechado_perdido"
                    valor_fechado = None
                elif "aguardando" in sit or "emitido" in sit or "tratamento" in sit:
                    status = "orcamento_enviado"
                    valor_fechado = None
                else:
                    status = "negociando"
                    valor_fechado = None

                data_entrada = d_ap or d_em or datetime.now().date()

                cur.execute("""
                    INSERT INTO oportunidades (
                        tenant_id, paciente_id, tratamento_id,
                        origem, status, crc_responsavel,
                        valor_orcado, valor_fechado,
                        data_entrada, data_ultima_atividade
                    ) VALUES (%s,%s,%s,'historico',%s,%s,%s,%s,%s,%s)
                """, (
                    tenant_id, paciente_id, tid,
                    status, vendedor,
                    valor, valor_fechado,
                    data_entrada, data_entrada,
                ))
                criadas += 1

    return {"criadas": criadas, "total": total}
