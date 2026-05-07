"""Conexão PostgreSQL e schema completo do OdontoMind."""
import os
import psycopg2
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


def _dsn() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL não configurada.")
    return url


@contextmanager
def get_conn():
    conn = psycopg2.connect(_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:

            # ----------------------------------------------------------------
            # Tenants (clínicas)
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id              TEXT PRIMARY KEY,
                    nome            TEXT NOT NULL,
                    slug            TEXT UNIQUE,
                    ativo           BOOLEAN DEFAULT TRUE,
                    plano           TEXT DEFAULT 'professional',
                    plano_validade  DATE,
                    co_usuario      TEXT,
                    co_senha        TEXT,
                    co_estab_id     TEXT,
                    criado_em       TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # ----------------------------------------------------------------
            # Usuários
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id          SERIAL PRIMARY KEY,
                    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    username    TEXT NOT NULL,
                    nome        TEXT NOT NULL,
                    email       TEXT,
                    senha_hash  TEXT NOT NULL,
                    papel       TEXT DEFAULT 'user',
                    funcao      TEXT,
                    ativo       BOOLEAN DEFAULT TRUE,
                    criado_em   TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(tenant_id, username)
                )
            """)

            # ----------------------------------------------------------------
            # Pacientes — uma entrada por pessoa, deduplicado por prontuario
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pacientes (
                    id                  SERIAL PRIMARY KEY,
                    tenant_id           TEXT NOT NULL,
                    prontuario_id       TEXT,
                    cpf                 TEXT,
                    nome                TEXT NOT NULL,
                    whatsapp            TEXT,
                    telefone            TEXT,
                    email               TEXT,
                    data_nascimento     DATE,
                    data_cadastro       DATE,
                    ultima_consulta     DATE,
                    captacao            TEXT,
                    campanha_origem     TEXT,
                    indicacao_por_id    INTEGER,
                    balanca_financeira  NUMERIC(12,2) DEFAULT 0,
                    cidade              TEXT,
                    status              TEXT DEFAULT 'ativo',
                    criado_em           TIMESTAMPTZ DEFAULT NOW(),
                    atualizado_em       TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_paciente_prontuario
                ON pacientes(tenant_id, prontuario_id)
                WHERE prontuario_id IS NOT NULL
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_paciente_cpf
                ON pacientes(tenant_id, cpf)
                WHERE cpf IS NOT NULL AND cpf <> ''
            """)

            # ----------------------------------------------------------------
            # Oportunidades — cada jornada comercial
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS oportunidades (
                    id                      SERIAL PRIMARY KEY,
                    tenant_id               TEXT NOT NULL,
                    paciente_id             INTEGER REFERENCES pacientes(id),
                    origem                  TEXT,
                    status                  TEXT DEFAULT 'lead_novo',
                    crc_responsavel         TEXT,
                    valor_orcado            NUMERIC(12,2),
                    valor_fechado           NUMERIC(12,2),
                    tratamento_id           INTEGER,
                    data_entrada            TIMESTAMPTZ DEFAULT NOW(),
                    data_ultima_atividade   TIMESTAMPTZ DEFAULT NOW(),
                    motivo_perda            TEXT,
                    observacoes             TEXT,
                    criado_em               TIMESTAMPTZ DEFAULT NOW(),
                    atualizado_em           TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # ----------------------------------------------------------------
            # Tratamentos — orçamentos e contratos do Controle Odonto
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tratamentos (
                    id                  SERIAL PRIMARY KEY,
                    tenant_id           TEXT NOT NULL,
                    paciente_id         INTEGER REFERENCES pacientes(id),
                    co_orcamento_id     TEXT,
                    co_contrato_id      TEXT,
                    tipo                TEXT,
                    dentista            TEXT,
                    vendedor            TEXT,
                    campanha_marketing  TEXT,
                    valor_total         NUMERIC(12,2),
                    valor_clinico       NUMERIC(12,2),
                    valor_orto          NUMERIC(12,2),
                    valor_manutencao    NUMERIC(12,2),
                    desconto            NUMERIC(12,2),
                    forma_pagamento     TEXT,
                    situacao_titulos    TEXT,
                    data_emissao        DATE,
                    data_aprovacao      DATE,
                    data_conclusao      DATE,
                    situacao            TEXT,
                    criado_em           TIMESTAMPTZ DEFAULT NOW(),
                    atualizado_em       TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_trat_orcamento
                ON tratamentos(tenant_id, co_orcamento_id)
                WHERE co_orcamento_id IS NOT NULL
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_trat_contrato
                ON tratamentos(tenant_id, co_contrato_id)
                WHERE co_contrato_id IS NOT NULL
            """)

            # ----------------------------------------------------------------
            # Procedimentos realizados
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS procedimentos (
                    id                  SERIAL PRIMARY KEY,
                    tenant_id           TEXT NOT NULL,
                    paciente_id         INTEGER REFERENCES pacientes(id),
                    tratamento_id       INTEGER REFERENCES tratamentos(id),
                    data_realizacao     DATE,
                    dentista            TEXT,
                    especialidade       TEXT,
                    nome_procedimento   TEXT,
                    valor               NUMERIC(12,2),
                    dente               TEXT,
                    face                TEXT,
                    situacao            TEXT DEFAULT 'Concluído',
                    observacoes         TEXT,
                    criado_em           TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # ----------------------------------------------------------------
            # Agendamentos (tempo real via webhooks CO)
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agendamentos (
                    id                  SERIAL PRIMARY KEY,
                    tenant_id           TEXT NOT NULL,
                    paciente_id         INTEGER REFERENCES pacientes(id),
                    co_agendamento_id   TEXT,
                    data_hora           TIMESTAMPTZ,
                    dentista            TEXT,
                    procedimento        TEXT,
                    status              TEXT DEFAULT 'agendado',
                    criado_em           TIMESTAMPTZ DEFAULT NOW(),
                    atualizado_em       TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_agendamento_co
                ON agendamentos(tenant_id, co_agendamento_id)
                WHERE co_agendamento_id IS NOT NULL
            """)

            # ----------------------------------------------------------------
            # Log de webhooks (auditoria)
            # ----------------------------------------------------------------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS webhook_log (
                    id          SERIAL PRIMARY KEY,
                    tenant_id   TEXT,
                    evento      TEXT,
                    payload     JSONB,
                    processado  BOOLEAN DEFAULT FALSE,
                    erro        TEXT,
                    criado_em   TIMESTAMPTZ DEFAULT NOW()
                )
            """)

    print("OdontoMind: schema inicializado.")


# ----------------------------------------------------------------
# Helpers de busca comuns
# ----------------------------------------------------------------

def buscar_paciente_por_prontuario(conn, tenant_id: str, prontuario_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND prontuario_id=%s",
            (tenant_id, prontuario_id),
        )
        row = cur.fetchone()
        return row[0] if row else None


def buscar_paciente_por_cpf(conn, tenant_id: str, cpf: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND cpf=%s",
            (tenant_id, cpf),
        )
        row = cur.fetchone()
        return row[0] if row else None


def buscar_paciente_por_telefone(conn, tenant_id: str, telefone: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM pacientes WHERE tenant_id=%s AND (whatsapp=%s OR telefone=%s) LIMIT 1",
            (tenant_id, telefone, telefone),
        )
        row = cur.fetchone()
        return row[0] if row else None


def buscar_tratamento_por_co_id(conn, tenant_id: str, co_id: str, campo: str = "co_orcamento_id"):
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id FROM tratamentos WHERE tenant_id=%s AND {campo}=%s",
            (tenant_id, co_id),
        )
        row = cur.fetchone()
        return row[0] if row else None
