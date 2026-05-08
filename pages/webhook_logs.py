"""Página de logs de webhooks recebidos."""
import json
import streamlit as st
from datetime import datetime, timedelta

from auth import require_papel
from database import get_conn


def _badge(texto: str, cor: str = "gray") -> str:
    return f'<span class="om-badge om-{cor}">{texto}</span>'


def show():
    require_papel(["master", "admin"])
    tenant_id = st.session_state.usuario["tenant_id"]

    st.title("Webhook Logs")
    st.markdown(
        '<div style="font-size:0.85rem;color:#6B7280;margin-top:-0.5rem;margin-bottom:1rem;">'
        'Eventos recebidos do Controle Odonto e outras integrações.</div>',
        unsafe_allow_html=True,
    )

    # Filtros
    col1, col2, col3, col4 = st.columns([1, 1, 2, 1])
    with col1:
        periodo = st.selectbox("Período", [1, 7, 30],
                               format_func=lambda x: f"Últimos {x} dia(s)")
    with col2:
        filtro_status = st.selectbox("Status", ["Todos", "Processado", "Erro"])
    with col3:
        filtro_evento = st.text_input("Filtrar evento", placeholder="ex: agendamento",
                                      label_visibility="collapsed")
    with col4:
        atualizar = st.button("↻ Atualizar", type="primary", use_container_width=True)

    if atualizar:
        st.rerun()

    # Consulta
    data_ini    = datetime.now() - timedelta(days=periodo)
    conditions  = ["tenant_id = %s", "criado_em >= %s"]
    params: list = [tenant_id, data_ini]

    if filtro_status == "Processado":
        conditions.append("processado = TRUE")
    elif filtro_status == "Erro":
        conditions.append("(processado = FALSE OR erro IS NOT NULL)")

    if filtro_evento.strip():
        conditions.append("evento ILIKE %s")
        params.append(f"%{filtro_evento.strip()}%")

    where = " AND ".join(conditions)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, evento, processado, erro, criado_em, payload
                    FROM webhook_log
                    WHERE {where}
                    ORDER BY criado_em DESC
                    LIMIT 200
                """, params)
                rows = cur.fetchall()
    except Exception as e:
        st.error(f"Erro ao consultar logs: {e}")
        return

    if not rows:
        st.info("Nenhum evento encontrado para o período selecionado.")
        return

    # Sumário rápido
    n_ok  = sum(1 for r in rows if r[2] and not r[3])
    n_err = sum(1 for r in rows if not r[2] or r[3])

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total",       len(rows))
    col_b.metric("Processados", n_ok)
    col_c.metric("Erros",       n_err)

    st.divider()

    for row in rows:
        log_id, evento, processado, erro, criado_em, payload_raw = row

        ok     = processado and not erro
        cor    = "green" if ok else "red"
        icone  = "✓" if ok else "✗"
        status_label = "OK" if ok else ("Erro" if erro else "Não processado")
        ts     = criado_em.strftime("%d/%m %H:%M:%S") if criado_em else "—"

        badge_status = _badge(f"{icone} {status_label}", cor)
        label = f"`{evento}` — {ts}"

        with st.expander(label, expanded=bool(erro)):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.markdown(
                    f'<span style="font-size:0.8rem;color:#6B7280;">ID {log_id}</span>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(badge_status, unsafe_allow_html=True)
            with c3:
                st.markdown(
                    f'<span style="font-size:0.8rem;color:#6B7280;">{ts}</span>',
                    unsafe_allow_html=True,
                )

            if erro:
                st.error(f"Erro: {erro}")

            if payload_raw:
                try:
                    data = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
                    st.json(data)
                except Exception:
                    st.code(str(payload_raw))
            else:
                st.caption("Payload vazio")
