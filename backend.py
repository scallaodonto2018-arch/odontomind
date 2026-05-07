"""
OdontoMind — Backend FastAPI
Recebe webhooks do Controle Odonto com uma rota por evento.

URLs para configurar no CO (substituir {tenant} por scalla-odonto):
  POST /webhook/{tenant}/co/cadastro-agendamento
  POST /webhook/{tenant}/co/alteracao-agendamento
  POST /webhook/{tenant}/co/cancelamento-agendamento
  POST /webhook/{tenant}/co/confirmou-agendamento
  POST /webhook/{tenant}/co/paciente-faltar
  POST /webhook/{tenant}/co/inicio-atendimento
  POST /webhook/{tenant}/co/cadastro-orcamento
  POST /webhook/{tenant}/co/orcamento-aprovado
  POST /webhook/{tenant}/co/cancelamento-orcamento
  POST /webhook/{tenant}/co/cadastro-paciente

Deploy: uvicorn backend:app --host 0.0.0.0 --port 8000
"""
import json
import os
from datetime import datetime

from fastapi import FastAPI, Request
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
# Helpers de extração de campos CO (nomes em português)
# ----------------------------------------------------------------

def _paciente_id_co(p: dict) -> str | None:
    return str_ou_none(
        p.get("Identificador do Paciente")
        or p.get("identificador do paciente")
        or p.get("PessoaId") or p.get("pessoaId")
    )

def _paciente_nome(p: dict) -> str | None:
    return str_ou_none(
        p.get("Nome do Paciente")
        or p.get("nome do paciente")
        or p.get("Nome") or p.get("nome")
    )

def _paciente_tel(p: dict) -> str | None:
    return normalizar_telefone(
        p.get("Telefone do Paciente")
        or p.get("telefone do paciente")
        or p.get("Telefone") or p.get("telefone")
        or p.get("Fone1") or p.get("consumidorPessoaFone1")
    )

def _dentista(p: dict) -> str | None:
    return str_ou_none(
        p.get("Nome do Profissional")
        or p.get("nome do profissional")
        or p.get("NomeDentista") or p.get("Dentista")
    )

def _ag_id(p: dict) -> str | None:
    return str_ou_none(
        p.get("Identificador do Agendamento")
        or p.get("identificador do agendamento")
        or p.get("Id") or p.get("id") or p.get("AgendamentoId")
    )

def _ag_data(p: dict):
    return normalizar_data(
        p.get("Data do Agendamento")
        or p.get("data do agendamento")
        or p.get("DataInicio") or p.get("Data")
    )

def _orc_id(p: dict) -> str | None:
    return str_ou_none(
        p.get("Identificador do Orçamento")
        or p.get("identificador do orçamento")
        or p.get("Id") or p.get("id") or p.get("OrcamentoId")
    )

def _orc_valor(p: dict) -> float | None:
    return normalizar_valor(
        p.get("Valor Total")
        or p.get("valor total")
        or p.get("ValorTotal") or p.get("Total")
    )


# ----------------------------------------------------------------
# Helper: garante paciente no banco
# ----------------------------------------------------------------

def _garantir_paciente(cur, tenant_id: str, payload: dict) -> int | None:
    prontuario = _paciente_id_co(payload)
    nome       = _paciente_nome(payload)
    whatsapp   = _paciente_tel(payload)

    if not nome and not prontuario:
        return None

    if prontuario:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND prontuario_id=%s",
            (tenant_id, prontuario),
        )
        row = cur.fetchone()
        if row:
            # Atualiza telefone se novo
            if whatsapp:
                cur.execute(
                    "UPDATE pacientes SET whatsapp=COALESCE(whatsapp,%s) WHERE id=%s",
                    (whatsapp, row[0]),
                )
            return row[0]

    if whatsapp:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND (whatsapp=%s OR telefone=%s) LIMIT 1",
            (tenant_id, whatsapp, whatsapp),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    if nome:
        cur.execute("""
            INSERT INTO pacientes (tenant_id, prontuario_id, nome, whatsapp)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, (tenant_id, prontuario, nome, whatsapp))
        return cur.fetchone()[0]

    return None


# ----------------------------------------------------------------
# Helper: log de webhook
# ----------------------------------------------------------------

def _log(tenant_id: str, evento: str, payload: dict, erro: str = None):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO webhook_log (tenant_id, evento, payload, processado, erro)
                    VALUES (%s,%s,%s,%s,%s)
                """, (tenant_id, evento,
                      json.dumps(payload, ensure_ascii=False, default=str),
                      erro is None, erro))
    except Exception:
        pass


# ----------------------------------------------------------------
# Rotas — uma por evento CO
# ----------------------------------------------------------------

@app.post("/webhook/{tenant_id}/co/cadastro-agendamento")
async def wh_cadastro_agendamento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "cadastro-agendamento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                paciente_id = _garantir_paciente(cur, tenant_id, payload)
                ag_id    = _ag_id(payload)
                data_hora = _ag_data(payload)
                dentista  = _dentista(payload)
                cur.execute("""
                    INSERT INTO agendamentos
                        (tenant_id, paciente_id, co_agendamento_id, data_hora, dentista, status)
                    VALUES (%s,%s,%s,%s,%s,'agendado')
                    ON CONFLICT (tenant_id, co_agendamento_id)
                    WHERE co_agendamento_id IS NOT NULL
                    DO UPDATE SET data_hora=EXCLUDED.data_hora,
                                  dentista=EXCLUDED.dentista,
                                  status='agendado',
                                  atualizado_em=NOW()
                """, (tenant_id, paciente_id, ag_id, data_hora, dentista))

                # Avança oportunidade ativa para 'agendado'
                if paciente_id:
                    cur.execute("""
                        UPDATE oportunidades SET status='agendado',
                            data_ultima_atividade=NOW(), atualizado_em=NOW()
                        WHERE tenant_id=%s AND paciente_id=%s
                          AND status NOT IN ('agendado','compareceu','fechado_ganho','fechado_perdido')
                        ORDER BY data_ultima_atividade DESC LIMIT 1
                    """, (tenant_id, paciente_id))
    except Exception as e:
        _log(tenant_id, "cadastro-agendamento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/alteracao-agendamento")
async def wh_alteracao_agendamento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "alteracao-agendamento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                ag_id = _ag_id(payload)
                if ag_id:
                    cur.execute("""
                        UPDATE agendamentos
                        SET data_hora=%s, dentista=%s, atualizado_em=NOW()
                        WHERE tenant_id=%s AND co_agendamento_id=%s
                    """, (_ag_data(payload), _dentista(payload), tenant_id, ag_id))
    except Exception as e:
        _log(tenant_id, "alteracao-agendamento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/cancelamento-agendamento")
async def wh_cancelamento_agendamento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "cancelamento-agendamento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                ag_id = _ag_id(payload)
                if ag_id:
                    cur.execute("""
                        UPDATE agendamentos SET status='cancelado', atualizado_em=NOW()
                        WHERE tenant_id=%s AND co_agendamento_id=%s
                        RETURNING paciente_id
                    """, (tenant_id, ag_id))
                    row = cur.fetchone()
                    if row and row[0]:
                        cur.execute("""
                            UPDATE oportunidades SET status='contato_feito',
                                data_ultima_atividade=NOW(), atualizado_em=NOW()
                            WHERE tenant_id=%s AND paciente_id=%s AND status='agendado'
                            ORDER BY data_ultima_atividade DESC LIMIT 1
                        """, (tenant_id, row[0]))
    except Exception as e:
        _log(tenant_id, "cancelamento-agendamento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/confirmou-agendamento")
async def wh_confirmou_agendamento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "confirmou-agendamento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                ag_id = _ag_id(payload)
                if ag_id:
                    cur.execute("""
                        UPDATE agendamentos SET status='confirmado', atualizado_em=NOW()
                        WHERE tenant_id=%s AND co_agendamento_id=%s
                    """, (tenant_id, ag_id))
    except Exception as e:
        _log(tenant_id, "confirmou-agendamento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/paciente-faltar")
async def wh_paciente_faltar(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "paciente-faltar", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                ag_id = _ag_id(payload)
                if ag_id:
                    cur.execute("""
                        UPDATE agendamentos SET status='faltou', atualizado_em=NOW()
                        WHERE tenant_id=%s AND co_agendamento_id=%s
                        RETURNING paciente_id
                    """, (tenant_id, ag_id))
                    row = cur.fetchone()
                    # Volta oportunidade para contato_feito para CRC reagir
                    if row and row[0]:
                        cur.execute("""
                            UPDATE oportunidades SET status='contato_feito',
                                data_ultima_atividade=NOW(), atualizado_em=NOW()
                            WHERE tenant_id=%s AND paciente_id=%s
                              AND status IN ('agendado','confirmado')
                            ORDER BY data_ultima_atividade DESC LIMIT 1
                        """, (tenant_id, row[0]))
    except Exception as e:
        _log(tenant_id, "paciente-faltar-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/inicio-atendimento")
async def wh_inicio_atendimento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "inicio-atendimento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                ag_id = _ag_id(payload)
                if ag_id:
                    cur.execute("""
                        UPDATE agendamentos SET status='compareceu', atualizado_em=NOW()
                        WHERE tenant_id=%s AND co_agendamento_id=%s
                        RETURNING paciente_id
                    """, (tenant_id, ag_id))
                    row = cur.fetchone()
                    if row and row[0]:
                        cur.execute("""
                            UPDATE oportunidades SET status='compareceu',
                                data_ultima_atividade=NOW(), atualizado_em=NOW()
                            WHERE tenant_id=%s AND paciente_id=%s
                              AND status IN ('agendado','confirmado')
                            ORDER BY data_ultima_atividade DESC LIMIT 1
                        """, (tenant_id, row[0]))
    except Exception as e:
        _log(tenant_id, "inicio-atendimento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/cadastro-orcamento")
async def wh_cadastro_orcamento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "cadastro-orcamento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                paciente_id = _garantir_paciente(cur, tenant_id, payload)
                orc_id  = _orc_id(payload)
                valor   = _orc_valor(payload)
                dentista = _dentista(payload)
                cur.execute("""
                    INSERT INTO tratamentos
                        (tenant_id, paciente_id, co_orcamento_id, tipo, dentista,
                         valor_total, data_emissao, situacao)
                    VALUES (%s,%s,%s,'orcamento',%s,%s,CURRENT_DATE,'emitido')
                    ON CONFLICT (tenant_id, co_orcamento_id)
                    WHERE co_orcamento_id IS NOT NULL
                    DO NOTHING
                """, (tenant_id, paciente_id, orc_id, dentista, valor))

                if paciente_id:
                    cur.execute("""
                        UPDATE oportunidades SET status='orcamento_enviado',
                            valor_orcado=%s, data_ultima_atividade=NOW(), atualizado_em=NOW()
                        WHERE tenant_id=%s AND paciente_id=%s
                          AND status IN ('compareceu','contato_feito','agendado')
                        ORDER BY data_ultima_atividade DESC LIMIT 1
                    """, (valor, tenant_id, paciente_id))
    except Exception as e:
        _log(tenant_id, "cadastro-orcamento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/orcamento-aprovado")
async def wh_orcamento_aprovado(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "orcamento-aprovado", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                orc_id = _orc_id(payload)
                valor  = _orc_valor(payload)
                cur.execute("""
                    UPDATE tratamentos SET situacao='aprovado',
                        data_aprovacao=CURRENT_DATE,
                        valor_total=COALESCE(%s, valor_total),
                        atualizado_em=NOW()
                    WHERE tenant_id=%s AND co_orcamento_id=%s
                    RETURNING paciente_id
                """, (valor, tenant_id, orc_id))
                row = cur.fetchone()
                if row and row[0]:
                    cur.execute("""
                        UPDATE oportunidades SET status='fechado_ganho',
                            valor_fechado=COALESCE(%s, valor_orcado),
                            data_ultima_atividade=NOW(), atualizado_em=NOW()
                        WHERE tenant_id=%s AND paciente_id=%s
                          AND status NOT IN ('fechado_ganho','fechado_perdido')
                        ORDER BY data_ultima_atividade DESC LIMIT 1
                    """, (valor, tenant_id, row[0]))
    except Exception as e:
        _log(tenant_id, "orcamento-aprovado-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/cancelamento-orcamento")
async def wh_cancelamento_orcamento(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "cancelamento-orcamento", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                orc_id = _orc_id(payload)
                cur.execute("""
                    UPDATE tratamentos SET situacao='cancelado', atualizado_em=NOW()
                    WHERE tenant_id=%s AND co_orcamento_id=%s
                    RETURNING paciente_id
                """, (tenant_id, orc_id))
                row = cur.fetchone()
                if row and row[0]:
                    cur.execute("""
                        UPDATE oportunidades SET status='fechado_perdido',
                            data_ultima_atividade=NOW(), atualizado_em=NOW()
                        WHERE tenant_id=%s AND paciente_id=%s
                          AND status NOT IN ('fechado_ganho','fechado_perdido')
                        ORDER BY data_ultima_atividade DESC LIMIT 1
                    """, (tenant_id, row[0]))
    except Exception as e:
        _log(tenant_id, "cancelamento-orcamento-erro", payload, str(e))
    return {"ok": True}


@app.post("/webhook/{tenant_id}/co/cadastro-paciente")
async def wh_cadastro_paciente(tenant_id: str, request: Request):
    payload = await _parse(request)
    _log(tenant_id, "cadastro-paciente", payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                paciente_id = _garantir_paciente(cur, tenant_id, payload)
                if paciente_id:
                    cur.execute("""
                        INSERT INTO oportunidades
                            (tenant_id, paciente_id, origem, status)
                        SELECT %s,%s,'co_cadastro','lead_novo'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM oportunidades
                            WHERE tenant_id=%s AND paciente_id=%s
                              AND status NOT IN ('fechado_ganho','fechado_perdido')
                        )
                    """, (tenant_id, paciente_id, tenant_id, paciente_id))
    except Exception as e:
        _log(tenant_id, "cadastro-paciente-erro", payload, str(e))
    return {"ok": True}


# ----------------------------------------------------------------
# Rota legada — compatibilidade com payload que inclui campo Evento
# ----------------------------------------------------------------

@app.post("/webhook/{tenant_id}/controle-odonto")
async def wh_legado(tenant_id: str, request: Request):
    """Rota original — redireciona pelo campo Evento no payload."""
    payload = await _parse(request)
    evento = (
        payload.get("Evento") or payload.get("evento") or "desconhecido"
    ).lower().replace(" ", "-").replace("_", "-")
    _log(tenant_id, f"legado/{evento}", payload)
    return {"ok": True, "evento": evento, "info": "use rotas específicas por evento"}


# ----------------------------------------------------------------
# API interna (usada pelo frontend Streamlit)
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
                    WHERE tenant_id=%s AND (nome ILIKE %s OR whatsapp ILIKE %s)
                    ORDER BY nome LIMIT %s OFFSET %s
                """, (tenant_id, like, like, limit, offset))
            else:
                cur.execute("""
                    SELECT id, nome, whatsapp, email, captacao, ultima_consulta, status
                    FROM pacientes WHERE tenant_id=%s
                    ORDER BY nome LIMIT %s OFFSET %s
                """, (tenant_id, limit, offset))
            cols = ["id","nome","whatsapp","email","captacao","ultima_consulta","status"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.patch("/api/oportunidades/{oportunidade_id}/status")
def atualizar_status_oportunidade(oportunidade_id: int, body: dict):
    novo_status = body.get("status")
    tenant_id   = body.get("tenant_id")
    if not novo_status or not tenant_id:
        raise Exception("status e tenant_id obrigatórios")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE oportunidades SET status=%s,
                    data_ultima_atividade=NOW(), atualizado_em=NOW()
                WHERE id=%s AND tenant_id=%s
            """, (novo_status, oportunidade_id, tenant_id))
    return {"ok": True}


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

async def _parse(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}
