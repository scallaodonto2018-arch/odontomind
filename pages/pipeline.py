"""Página de pipeline comercial — funil de oportunidades."""
import streamlit as st
from datetime import datetime, timedelta
from auth import require_auth
from database import get_conn


# Ordem e rótulos dos status do funil
STATUSES = [
    ("lead_novo",          "Lead Novo",         "🔵"),
    ("contato_feito",      "Contato Feito",      "🟡"),
    ("agendado",           "Agendado",           "🟠"),
    ("compareceu",         "Compareceu",         "🟣"),
    ("orcamento_enviado",  "Orçamento Enviado",  "🔷"),
    ("negociando",         "Negociando",         "🟤"),
    ("fechado_ganho",      "Fechado Ganho",      "🟢"),
    ("fechado_perdido",    "Fechado Perdido",    "🔴"),
]
STATUS_KEYS = [s[0] for s in STATUSES]
STATUS_LABELS = {s[0]: s[1] for s in STATUSES}
STATUS_ICONS = {s[0]: s[2] for s in STATUSES}


def _carregar_pipeline(tenant_id: str, periodo_dias: int, origem: str) -> dict:
    """Retorna oportunidades agrupadas por status."""
    data_ini = (datetime.now() - timedelta(days=periodo_dias)).date()
    conditions = ["o.tenant_id=%s", "o.data_entrada >= %s"]
    params = [tenant_id, data_ini]
    if origem and origem != "Todos":
        conditions.append("o.origem=%s")
        params.append(origem)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT o.id, o.status, o.origem, o.crc_responsavel,
                       o.valor_orcado, o.valor_fechado,
                       o.data_entrada, o.data_ultima_atividade, o.observacoes,
                       p.nome, p.whatsapp, p.id as paciente_id
                FROM oportunidades o
                LEFT JOIN pacientes p ON p.id = o.paciente_id
                WHERE {where}
                ORDER BY o.data_ultima_atividade DESC
            """, params)
            cols = ["id","status","origem","crc","v_orc","v_fec",
                    "dt_ent","dt_ult","obs","paciente","whatsapp","paciente_id"]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    grupos = {k: [] for k in STATUS_KEYS}
    for r in rows:
        st = r["status"]
        if st in grupos:
            grupos[st].append(r)
        else:
            grupos.setdefault(st, []).append(r)
    return grupos


def _metricas_funil(tenant_id: str) -> dict:
    """Métricas do mês atual."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            hoje = datetime.now().date()
            inicio_mes = hoje.replace(day=1)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status != 'fechado_perdido') as ativos,
                    COUNT(*) FILTER (WHERE status = 'fechado_ganho') as ganhos,
                    COUNT(*) FILTER (WHERE status = 'fechado_perdido') as perdidos,
                    COALESCE(SUM(valor_fechado) FILTER (WHERE status = 'fechado_ganho'), 0) as receita,
                    COALESCE(AVG(valor_fechado) FILTER (WHERE status = 'fechado_ganho'), 0) as ticket
                FROM oportunidades
                WHERE tenant_id=%s AND data_entrada >= %s
            """, (tenant_id, inicio_mes))
            row = cur.fetchone()
    return {
        "ativos": row[0], "ganhos": row[1], "perdidos": row[2],
        "receita": row[3], "ticket": row[4],
    }


def _card_oportunidade(oport: dict, tenant_id: str):
    """Renderiza card de uma oportunidade."""
    icon = STATUS_ICONS.get(oport["status"], "⚫")
    nome = oport.get("paciente") or "Sem nome"
    whatsapp = oport.get("whatsapp") or ""
    origem = oport.get("origem") or "—"
    v_orc = oport.get("v_orc")
    dt_ult = oport.get("dt_ult")

    with st.container(border=True):
        st.markdown(f"**{nome}**")
        if whatsapp:
            st.caption(f"📱 {whatsapp[:2]} {whatsapp[2:4]} {whatsapp[4:]}" if len(whatsapp) >= 11 else whatsapp)
        st.caption(f"Origem: {origem}")
        if v_orc:
            st.caption(f"Orçado: R$ {v_orc:,.2f}")
        if dt_ult:
            dias = (datetime.now() - dt_ult).days if hasattr(dt_ult, 'timetuple') else 0
            if dias > 3:
                st.caption(f"⚠️ {dias}d sem atividade")

        novo_status = st.selectbox(
            "Mover para",
            STATUS_KEYS,
            index=STATUS_KEYS.index(oport["status"]) if oport["status"] in STATUS_KEYS else 0,
            format_func=lambda k: STATUS_LABELS.get(k, k),
            key=f"mv_{oport['id']}",
            label_visibility="collapsed",
        )

        if novo_status != oport["status"]:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE oportunidades
                        SET status=%s, data_ultima_atividade=NOW(), atualizado_em=NOW()
                        WHERE id=%s AND tenant_id=%s
                    """, (novo_status, oport["id"], tenant_id))
            st.rerun()


def show():
    usuario = require_auth()
    tenant_id = usuario["tenant_id"]

    st.title("Pipeline Comercial")

    # Controles
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        periodo = st.selectbox("Período", [30, 60, 90, 180, 365], format_func=lambda x: f"Últimos {x} dias")
    with col2:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT origem FROM oportunidades WHERE tenant_id=%s AND origem IS NOT NULL ORDER BY origem",
                        (tenant_id,),
                    )
                    origens = ["Todos"] + [r[0] for r in cur.fetchall()]
        except Exception:
            origens = ["Todos"]
        origem_filtro = st.selectbox("Origem", origens)
    with col3:
        if st.button("Nova oportunidade"):
            st.session_state.nova_oport = True

    # Nova oportunidade
    if st.session_state.get("nova_oport"):
        with st.expander("Criar nova oportunidade", expanded=True):
            with st.form("form_nova_oport"):
                nome_pac = st.text_input("Nome do paciente")
                whatsapp = st.text_input("WhatsApp")
                origem_nova = st.selectbox("Origem", ["meta_ads","google_ads","indicacao","organico",
                                                       "reativacao","whatsapp_ativo","co_cadastro","outro"])
                crc = st.text_input("CRC Responsável")
                obs = st.text_area("Observações")
                col_s, col_c = st.columns(2)
                salvar = col_s.form_submit_button("Salvar", type="primary")
                cancelar = col_c.form_submit_button("Cancelar")

            if cancelar:
                del st.session_state.nova_oport
                st.rerun()

            if salvar and nome_pac:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        # Tenta encontrar paciente por nome
                        like = nome_pac.strip()[:30] + "%"
                        cur.execute(
                            "SELECT id FROM pacientes WHERE tenant_id=%s AND nome ILIKE %s LIMIT 1",
                            (tenant_id, like),
                        )
                        row = cur.fetchone()
                        if row:
                            paciente_id = row[0]
                        else:
                            # Cria paciente novo
                            from importers.utils import normalizar_telefone
                            tel = normalizar_telefone(whatsapp)
                            cur.execute("""
                                INSERT INTO pacientes (tenant_id, nome, whatsapp)
                                VALUES (%s,%s,%s) RETURNING id
                            """, (tenant_id, nome_pac, tel))
                            paciente_id = cur.fetchone()[0]

                        cur.execute("""
                            INSERT INTO oportunidades
                                (tenant_id, paciente_id, origem, crc_responsavel, observacoes, status)
                            VALUES (%s,%s,%s,%s,%s,'lead_novo')
                        """, (tenant_id, paciente_id, origem_nova, crc or None, obs or None))

                del st.session_state.nova_oport
                st.success("Oportunidade criada!")
                st.rerun()

    # Métricas do mês
    m = _metricas_funil(tenant_id)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ativos", m["ativos"])
    c2.metric("Fechados (mês)", m["ganhos"])
    c3.metric("Perdidos (mês)", m["perdidos"])
    c4.metric("Receita (mês)", f"R$ {m['receita']:,.0f}")
    c5.metric("Ticket médio", f"R$ {m['ticket']:,.0f}")

    st.divider()

    # Funil
    grupos = _carregar_pipeline(tenant_id, periodo, origem_filtro)

    # Exibe apenas status com registros + os status principais sempre visíveis
    status_visiveis = [
        ("lead_novo", "agendado", "compareceu", "negociando"),
        ("fechado_ganho", "fechado_perdido"),
    ]

    # View por colunas (todos os status)
    st.subheader("Funil")
    tabs = st.tabs([f"{STATUS_ICONS[k]} {STATUS_LABELS[k]} ({len(grupos.get(k,[]))})" for k in STATUS_KEYS])
    for tab, (key, label, icon) in zip(tabs, STATUSES):
        with tab:
            oports = grupos.get(key, [])
            if not oports:
                st.caption("Nenhuma oportunidade neste estágio.")
                continue
            for oport in oports:
                _card_oportunidade(oport, tenant_id)
