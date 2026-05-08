"""Página de pipeline comercial — funil de oportunidades."""
import streamlit as st
from datetime import datetime, timedelta, timezone
from auth import require_auth
from database import get_conn


STATUSES = [
    ("lead_novo",          "Lead Novo",         "om-blue"),
    ("contato_feito",      "Contato Feito",      "om-yellow"),
    ("agendado",           "Agendado",           "om-orange"),
    ("compareceu",         "Compareceu",         "om-purple"),
    ("orcamento_enviado",  "Orçamento Enviado",  "om-indigo"),
    ("negociando",         "Negociando",         "om-teal"),
    ("fechado_ganho",      "Fechado Ganho",      "om-green"),
    ("fechado_perdido",    "Fechado Perdido",    "om-red"),
]
STATUS_KEYS   = [s[0] for s in STATUSES]
STATUS_LABELS = {s[0]: s[1] for s in STATUSES}
STATUS_COR    = {s[0]: s[2] for s in STATUSES}

TAB_ICONS = {
    "lead_novo": "🔵", "contato_feito": "🟡", "agendado": "🟠",
    "compareceu": "🟣", "orcamento_enviado": "🔷", "negociando": "🟤",
    "fechado_ganho": "🟢", "fechado_perdido": "🔴",
}

ORIGEM_LABEL = {
    "meta_ads": "Meta Ads", "google_ads": "Google", "indicacao": "Indicação",
    "organico": "Orgânico", "reativacao": "Reativação", "whatsapp_ativo": "WhatsApp",
    "co_cadastro": "CO", "outro": "Outro",
}


def _badge(texto: str, cor: str = "gray") -> str:
    return f'<span class="om-badge om-{cor}">{texto}</span>'


def _carregar_pipeline(tenant_id: str, periodo_dias: int, origem: str) -> dict:
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
        s = r["status"]
        if s in grupos:
            grupos[s].append(r)
        else:
            grupos.setdefault(s, []).append(r)
    return grupos


def _metricas_funil(tenant_id: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            hoje = datetime.now().date()
            inicio_mes = hoje.replace(day=1)

            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status NOT IN ('fechado_ganho','fechado_perdido')) as ativos,
                    COUNT(*) FILTER (WHERE status = 'fechado_perdido') as perdidos
                FROM oportunidades
                WHERE tenant_id=%s AND data_entrada >= %s
            """, (tenant_id, inicio_mes))
            r_oport = cur.fetchone()

            cur.execute("""
                SELECT
                    COUNT(*) as contratos,
                    COALESCE(SUM(valor_total), 0) as total_liquido,
                    COALESCE(AVG(valor_total), 0) as ticket_medio
                FROM tratamentos
                WHERE tenant_id=%s
                  AND tipo = 'contrato'
                  AND data_emissao >= %s
            """, (tenant_id, inicio_mes))
            r_trat = cur.fetchone()

    return {
        "ativos":        r_oport[0],
        "perdidos":      r_oport[1],
        "contratos":     r_trat[0],
        "total_liquido": r_trat[1],
        "ticket_medio":  r_trat[2],
    }


def _fmt_brl(valor) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _card_oportunidade(oport: dict, tenant_id: str):
    nome    = oport.get("paciente") or "Sem nome"
    whatsapp = oport.get("whatsapp") or ""
    origem  = oport.get("origem") or ""
    v_orc   = oport.get("v_orc")
    dt_ult  = oport.get("dt_ult")
    status  = oport.get("status", "lead_novo")

    cor            = STATUS_COR.get(status, "om-gray").replace("om-", "")
    origem_label   = ORIGEM_LABEL.get(origem, origem) if origem else ""

    with st.container(border=True):
        col_info, col_action = st.columns([3, 2])

        with col_info:
            badge_status = _badge(STATUS_LABELS.get(status, status), cor)
            st.markdown(
                f'<div style="margin-bottom:0.25rem;">'
                f'<span style="font-size:0.925rem;font-weight:600;color:#111827;">{nome}</span>'
                f'&nbsp;&nbsp;{badge_status}</div>',
                unsafe_allow_html=True,
            )

            meta = []
            if whatsapp:
                tel = f"{whatsapp[:2]} {whatsapp[2:4]} {whatsapp[4:]}" if len(whatsapp) >= 11 else whatsapp
                meta.append(f"📱 {tel}")
            if origem_label:
                meta.append(f"via {origem_label}")
            if meta:
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#6B7280;">{" · ".join(meta)}</div>',
                    unsafe_allow_html=True,
                )

            if v_orc:
                st.markdown(
                    f'<div style="font-size:0.875rem;font-weight:600;color:#059669;margin-top:0.2rem;">'
                    f'{_fmt_brl(v_orc)}</div>',
                    unsafe_allow_html=True,
                )

            if dt_ult:
                try:
                    dias = (datetime.now(timezone.utc) - dt_ult).days if hasattr(dt_ult, "timetuple") else 0
                    if dias > 3:
                        st.markdown(
                            f'<div style="margin-top:0.3rem;">{_badge(f"⚠ {dias}d inativo", "red")}</div>',
                            unsafe_allow_html=True,
                        )
                except Exception:
                    pass

        with col_action:
            novo_status = st.selectbox(
                "Mover",
                STATUS_KEYS,
                index=STATUS_KEYS.index(status) if status in STATUS_KEYS else 0,
                format_func=lambda k: STATUS_LABELS.get(k, k),
                key=f"mv_{oport['id']}",
                label_visibility="collapsed",
            )
            if novo_status != status:
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
        periodo = st.selectbox("Período", [30, 60, 90, 180, 365],
                               format_func=lambda x: f"Últimos {x} dias")
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
        if st.button("+ Nova oportunidade", type="primary"):
            st.session_state.nova_oport = True

    # Nova oportunidade
    if st.session_state.get("nova_oport"):
        with st.expander("Criar nova oportunidade", expanded=True):
            with st.form("form_nova_oport"):
                col_a, col_b = st.columns(2)
                nome_pac     = col_a.text_input("Nome do paciente")
                whatsapp     = col_b.text_input("WhatsApp")
                origem_nova  = col_a.selectbox("Origem", ["meta_ads","google_ads","indicacao","organico",
                                                           "reativacao","whatsapp_ativo","co_cadastro","outro"])
                crc          = col_b.text_input("CRC Responsável")
                obs          = st.text_area("Observações")
                col_s, col_c = st.columns(2)
                salvar   = col_s.form_submit_button("Salvar", type="primary")
                cancelar = col_c.form_submit_button("Cancelar")

            if cancelar:
                del st.session_state.nova_oport
                st.rerun()

            if salvar and nome_pac:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        like = nome_pac.strip()[:30] + "%"
                        cur.execute(
                            "SELECT id FROM pacientes WHERE tenant_id=%s AND nome ILIKE %s LIMIT 1",
                            (tenant_id, like),
                        )
                        row = cur.fetchone()
                        if row:
                            paciente_id = row[0]
                        else:
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
    c1.metric("Em andamento",        m["ativos"])
    c2.metric("Contratos (mês)",      m["contratos"])
    c3.metric("Perdidos (mês)",       m["perdidos"])
    c4.metric("Total Líquido (mês)",  _fmt_brl(m["total_liquido"]))
    c5.metric("Ticket Médio",         _fmt_brl(m["ticket_medio"]))

    st.divider()

    # Funil em abas
    grupos = _carregar_pipeline(tenant_id, periodo, origem_filtro)

    tabs = st.tabs([
        f"{TAB_ICONS[k]} {STATUS_LABELS[k]} ({len(grupos.get(k, []))})"
        for k in STATUS_KEYS
    ])
    for tab, (key, label, _) in zip(tabs, STATUSES):
        with tab:
            oports = grupos.get(key, [])
            if not oports:
                st.markdown(
                    '<div style="color:#9CA3AF;font-size:0.85rem;padding:1rem 0;">'
                    'Nenhuma oportunidade neste estágio.</div>',
                    unsafe_allow_html=True,
                )
                continue
            for oport in oports:
                _card_oportunidade(oport, tenant_id)
