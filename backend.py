"""
OdontoMind — Backend FastAPI
Recebe webhooks do Controle Odonto e expõe API interna para o frontend.

Deploy: uvicorn backend:app --host 0.0.0.0 --port 8000
"""
import json
import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from database import get_conn, init_db
from importers.utils import normalizar_telefone, normalizar_data, normalizar_valor, str_ou_none

load_dotenv()

app = FastAPI(title="OdontoMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


# ----------------------------------------------------------------
# Health check
# ----------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print(f"Aviso: init_db falhou — {e}")


# ----------------------------------------------------------------
# Webhook do Controle Odonto
# POST /webhook/{tenant_id}/controle-odonto
# ----------------------------------------------------------------

@app.post("/webhook/{tenant_id}/controle-odonto")
async def webhook_co(tenant_id: str, request: Request):
    """
    Recebe todos os eventos do Controle Odonto.
    CO envia JSON com campo 'Evento' (ou 'evento') identificando o tipo.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    evento = (
        payload.get("Evento")
        or payload.get("evento")
        or payload.get("Event")
        or "desconhecido"
    )

    # Salva log para auditoria independente do processamento
    _log_webhook(tenant_id, evento, payload)

    handler = _HANDLERS.get(evento) or _HANDLERS.get(evento.lower())
    if handler:
        try:
            handler(tenant_id, payload)
            _marcar_webhook_processado(tenant_id, evento)
        except Exception as e:
            _marcar_webhook_erro(tenant_id, evento, str(e))
            print(f"[webhook] Erro ao processar {evento}: {e}")

    return {"ok": True, "evento": evento}


# ----------------------------------------------------------------
# Handlers por tipo de evento
# ----------------------------------------------------------------

def _handle_cadastro_agendamento(tenant_id: str, payload: dict):
    ag = _extrair_agendamento(payload)
    if not ag:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            paciente_id = _garantir_paciente(cur, tenant_id, payload)
            cur.execute("""
                INSERT INTO agendamentos (
                    tenant_id, paciente_id, co_agendamento_id,
                    data_hora, dentista, procedimento, status
                ) VALUES (%s,%s,%s,%s,%s,%s,'agendado')
                ON CONFLICT (tenant_id, co_agendamento_id)
                WHERE co_agendamento_id IS NOT NULL
                DO UPDATE SET
                    data_hora = EXCLUDED.data_hora,
                    dentista = EXCLUDED.dentista,
                    procedimento = EXCLUDED.procedimento,
                    status = 'agendado',
                    atualizado_em = NOW()
            """, (tenant_id, paciente_id, ag["id"], ag["data_hora"], ag["dentista"], ag["procedimento"]))


def _handle_alteracao_agendamento(tenant_id: str, payload: dict):
    ag = _extrair_agendamento(payload)
    if not ag or not ag.get("id"):
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agendamentos
                SET data_hora=%s, dentista=%s, procedimento=%s, atualizado_em=NOW()
                WHERE tenant_id=%s AND co_agendamento_id=%s
            """, (ag["data_hora"], ag["dentista"], ag["procedimento"], tenant_id, ag["id"]))


def _handle_cancelamento_agendamento(tenant_id: str, payload: dict):
    ag_id = _extrair_id_agendamento(payload)
    if not ag_id:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agendamentos SET status='cancelado', atualizado_em=NOW()
                WHERE tenant_id=%s AND co_agendamento_id=%s
            """, (tenant_id, ag_id))
            # Atualiza oportunidade associada
            cur.execute("""
                UPDATE oportunidades o
                SET status='lead_novo', data_ultima_atividade=NOW(), atualizado_em=NOW()
                FROM pacientes p
                JOIN agendamentos a ON a.paciente_id = p.id
                WHERE o.paciente_id = p.id
                  AND o.tenant_id = %s
                  AND a.co_agendamento_id = %s
                  AND o.status = 'agendado'
            """, (tenant_id, ag_id))


def _handle_paciente_faltar(tenant_id: str, payload: dict):
    ag_id = _extrair_id_agendamento(payload)
    if not ag_id:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agendamentos SET status='faltou', atualizado_em=NOW()
                WHERE tenant_id=%s AND co_agendamento_id=%s
            """, (tenant_id, ag_id))


def _handle_confirmou_agendamento(tenant_id: str, payload: dict):
    ag_id = _extrair_id_agendamento(payload)
    if not ag_id:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agendamentos SET status='confirmado', atualizado_em=NOW()
                WHERE tenant_id=%s AND co_agendamento_id=%s
            """, (tenant_id, ag_id))


def _handle_inicio_atendimento(tenant_id: str, payload: dict):
    ag_id = _extrair_id_agendamento(payload)
    if not ag_id:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agendamentos SET status='compareceu', atualizado_em=NOW()
                WHERE tenant_id=%s AND co_agendamento_id=%s
            """, (tenant_id, ag_id))
            # Avança oportunidade para 'compareceu'
            cur.execute("""
                UPDATE oportunidades o
                SET status='compareceu', data_ultima_atividade=NOW(), atualizado_em=NOW()
                FROM pacientes p
                JOIN agendamentos a ON a.paciente_id = p.id
                WHERE o.paciente_id = p.id
                  AND o.tenant_id = %s
                  AND a.co_agendamento_id = %s
                  AND o.status IN ('agendado', 'contato_feito')
            """, (tenant_id, ag_id))


def _handle_orcamento_aprovado(tenant_id: str, payload: dict):
    """Orçamento aprovado = contrato assinado. Fecha oportunidade."""
    co_orc_id = _extrair_id_orcamento(payload)
    valor = _extrair_valor_orcamento(payload)
    data_aprov = datetime.utcnow().date()

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Atualiza tratamento
            if co_orc_id:
                cur.execute("""
                    UPDATE tratamentos
                    SET situacao='aprovado', data_aprovacao=%s,
                        valor_total=COALESCE(%s, valor_total), atualizado_em=NOW()
                    WHERE tenant_id=%s AND co_orcamento_id=%s
                    RETURNING paciente_id
                """, (data_aprov, valor, tenant_id, co_orc_id))
                row = cur.fetchone()
                paciente_id = row[0] if row else None

                if paciente_id:
                    # Fecha oportunidade ativa do paciente
                    cur.execute("""
                        UPDATE oportunidades
                        SET status='fechado_ganho',
                            valor_fechado=COALESCE(%s, valor_orcado),
                            data_ultima_atividade=NOW(),
                            atualizado_em=NOW()
                        WHERE tenant_id=%s AND paciente_id=%s
                          AND status NOT IN ('fechado_ganho','fechado_perdido')
                        ORDER BY data_ultima_atividade DESC
                        LIMIT 1
                    """, (valor, tenant_id, paciente_id))


def _handle_cancelamento_orcamento(tenant_id: str, payload: dict):
    co_orc_id = _extrair_id_orcamento(payload)
    if not co_orc_id:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE tratamentos SET situacao='cancelado', atualizado_em=NOW()
                WHERE tenant_id=%s AND co_orcamento_id=%s
                RETURNING paciente_id
            """, (tenant_id, co_orc_id))
            row = cur.fetchone()
            if row and row[0]:
                cur.execute("""
                    UPDATE oportunidades
                    SET status='fechado_perdido', data_ultima_atividade=NOW(), atualizado_em=NOW()
                    WHERE tenant_id=%s AND paciente_id=%s
                      AND status NOT IN ('fechado_ganho','fechado_perdido')
                    ORDER BY data_ultima_atividade DESC
                    LIMIT 1
                """, (tenant_id, row[0]))


def _handle_cadastro_paciente(tenant_id: str, payload: dict):
    """Novo paciente cadastrado no CO — cria lead_novo."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            paciente_id = _garantir_paciente(cur, tenant_id, payload)
            if paciente_id:
                # Cria oportunidade se não houver ativa
                cur.execute("""
                    SELECT id FROM oportunidades
                    WHERE tenant_id=%s AND paciente_id=%s
                      AND status NOT IN ('fechado_ganho','fechado_perdido')
                    LIMIT 1
                """, (tenant_id, paciente_id))
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO oportunidades (tenant_id, paciente_id, origem, status)
                        VALUES (%s, %s, 'co_cadastro', 'lead_novo')
                    """, (tenant_id, paciente_id))


# Mapeamento de eventos para handlers
_HANDLERS = {
    # Agendamentos
    "CadastroAgendamento": _handle_cadastro_agendamento,
    "cadastroagendamento": _handle_cadastro_agendamento,
    "AlteracaoAgendamento": _handle_alteracao_agendamento,
    "alteracaoagendamento": _handle_alteracao_agendamento,
    "CancelamentoAgendamento": _handle_cancelamento_agendamento,
    "cancelamentoagendamento": _handle_cancelamento_agendamento,
    "ConfirmouAgendamento": _handle_confirmou_agendamento,
    "confirmouagendamento": _handle_confirmou_agendamento,
    "PacienteFaltar": _handle_paciente_faltar,
    "pacientefaltar": _handle_paciente_faltar,
    "InicioAtendimento": _handle_inicio_atendimento,
    "inicioatendimento": _handle_inicio_atendimento,
    # Orçamentos
    "OrcamentoAprovado": _handle_orcamento_aprovado,
    "orcamentoaprovado": _handle_orcamento_aprovado,
    "CancelamentoOrcamento": _handle_cancelamento_orcamento,
    "cancelamentoorcamento": _handle_cancelamento_orcamento,
    # Paciente
    "CadastroPaciente": _handle_cadastro_paciente,
    "cadastropaciente": _handle_cadastro_paciente,
}


# ----------------------------------------------------------------
# API endpoints (usados pelo frontend Streamlit via requests)
# ----------------------------------------------------------------

@app.get("/api/pacientes/{tenant_id}")
def listar_pacientes(tenant_id: str, busca: str = "", limit: int = 100, offset: int = 0):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if busca:
                like = f"%{busca}%"
                cur.execute("""
                    SELECT id, nome, whatsapp, email, captacao, ultima_consulta, status
                    FROM pacientes
                    WHERE tenant_id=%s AND (nome ILIKE %s OR whatsapp ILIKE %s OR email ILIKE %s)
                    ORDER BY nome LIMIT %s OFFSET %s
                """, (tenant_id, like, like, like, limit, offset))
            else:
                cur.execute("""
                    SELECT id, nome, whatsapp, email, captacao, ultima_consulta, status
                    FROM pacientes WHERE tenant_id=%s
                    ORDER BY nome LIMIT %s OFFSET %s
                """, (tenant_id, limit, offset))
            cols = ["id","nome","whatsapp","email","captacao","ultima_consulta","status"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.get("/api/pipeline/{tenant_id}")
def pipeline(tenant_id: str):
    """Retorna oportunidades agrupadas por status."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, o.status, o.origem, o.crc_responsavel,
                       o.valor_orcado, o.valor_fechado,
                       o.data_entrada, o.data_ultima_atividade,
                       p.nome as paciente_nome, p.whatsapp, p.id as paciente_id
                FROM oportunidades o
                LEFT JOIN pacientes p ON p.id = o.paciente_id
                WHERE o.tenant_id=%s
                  AND o.status NOT IN ('fechado_ganho','fechado_perdido')
                ORDER BY o.data_ultima_atividade DESC
            """, (tenant_id,))
            cols = ["id","status","origem","crc_responsavel","valor_orcado","valor_fechado",
                    "data_entrada","data_ultima_atividade","paciente_nome","whatsapp","paciente_id"]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            # Converte datas para string
            for r in rows:
                for k in ("data_entrada","data_ultima_atividade"):
                    if r[k]:
                        r[k] = str(r[k])

            return rows


@app.patch("/api/oportunidades/{oportunidade_id}/status")
def atualizar_status_oportunidade(oportunidade_id: int, body: dict):
    novo_status = body.get("status")
    tenant_id = body.get("tenant_id")
    if not novo_status or not tenant_id:
        raise HTTPException(400, "status e tenant_id são obrigatórios")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE oportunidades
                SET status=%s, data_ultima_atividade=NOW(), atualizado_em=NOW()
                WHERE id=%s AND tenant_id=%s
            """, (novo_status, oportunidade_id, tenant_id))
    return {"ok": True}


# ----------------------------------------------------------------
# Helpers internos
# ----------------------------------------------------------------

def _log_webhook(tenant_id: str, evento: str, payload: dict):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO webhook_log (tenant_id, evento, payload)
                    VALUES (%s, %s, %s)
                """, (tenant_id, evento, json.dumps(payload, ensure_ascii=False)))
    except Exception:
        pass


def _marcar_webhook_processado(tenant_id: str, evento: str):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE webhook_log SET processado=TRUE
                    WHERE tenant_id=%s AND evento=%s AND processado=FALSE
                    ORDER BY criado_em DESC LIMIT 1
                """, (tenant_id, evento))
    except Exception:
        pass


def _marcar_webhook_erro(tenant_id: str, evento: str, erro: str):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE webhook_log SET erro=%s
                    WHERE tenant_id=%s AND evento=%s AND processado=FALSE
                    ORDER BY criado_em DESC LIMIT 1
                """, (erro, tenant_id, evento))
    except Exception:
        pass


def _extrair_agendamento(payload: dict) -> dict | None:
    """Extrai campos de agendamento independente da estrutura do payload."""
    data = payload.get("Agendamento") or payload.get("agendamento") or payload
    if not data:
        return None
    ag_id = str_ou_none(data.get("Id") or data.get("id") or data.get("AgendamentoId"))
    data_hora_raw = data.get("DataInicio") or data.get("dataInicio") or data.get("Data")
    data_hora = normalizar_data(data_hora_raw)
    dentista = str_ou_none(data.get("NomeDentista") or data.get("nomeDentista") or data.get("Dentista"))
    procedimento = str_ou_none(data.get("NomeProcedimento") or data.get("Procedimento"))
    return {"id": ag_id, "data_hora": data_hora, "dentista": dentista, "procedimento": procedimento}


def _extrair_id_agendamento(payload: dict) -> str | None:
    data = payload.get("Agendamento") or payload.get("agendamento") or payload
    return str_ou_none(data.get("Id") or data.get("id") or data.get("AgendamentoId"))


def _extrair_id_orcamento(payload: dict) -> str | None:
    data = payload.get("Orcamento") or payload.get("orcamento") or payload
    return str_ou_none(data.get("Id") or data.get("id") or data.get("OrcamentoId"))


def _extrair_valor_orcamento(payload: dict) -> float | None:
    data = payload.get("Orcamento") or payload.get("orcamento") or payload
    raw = data.get("ValorTotal") or data.get("valorTotal") or data.get("Total")
    return normalizar_valor(raw)


def _garantir_paciente(cur, tenant_id: str, payload: dict) -> int | None:
    """Cria ou encontra paciente a partir de dados do webhook."""
    data = (
        payload.get("Paciente") or payload.get("paciente")
        or payload.get("Consumidor") or payload.get("consumidor")
        or payload
    )
    prontuario = str_ou_none(
        data.get("PessoaId") or data.get("pessoaId")
        or data.get("Prontuario") or data.get("prontuario")
    )
    nome = str_ou_none(data.get("Nome") or data.get("nome") or data.get("NomePaciente"))
    whatsapp = normalizar_telefone(
        data.get("Fone1") or data.get("fone1")
        or data.get("Telefone") or data.get("consumidorPessoaFone1")
    )

    if not nome and not prontuario:
        return None

    # Tenta localizar por prontuário
    if prontuario:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND prontuario_id=%s",
            (tenant_id, prontuario),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Tenta por WhatsApp
    if whatsapp:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND (whatsapp=%s OR telefone=%s) LIMIT 1",
            (tenant_id, whatsapp, whatsapp),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Cria novo
    if nome:
        cur.execute("""
            INSERT INTO pacientes (tenant_id, prontuario_id, nome, whatsapp)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (tenant_id, prontuario, nome, whatsapp))
        row = cur.fetchone()
        return row[0] if row else None

    return None
