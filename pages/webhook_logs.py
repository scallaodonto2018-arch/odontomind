"""Página de logs de webhooks recebidos."""
import json
import streamlit as st
from datetime import datetime, timedelta

from auth import require_papel
from database import get_conn


def show():
    require_papel(["master", "admin"])
    tenant_id = st.session_state.usuario["tenant_id"]

    st.title("Logs de Webhook")
    st.caption("Eventos recebidos do Controle Odonto e outras integrações.")

    # Filtros
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        periodo = st.selectbox("Período", [1, 7, 30], format_func=lambda x: f"Últimos {x} dia(s)")
    with col2:
        filtro_status = st.selectbox("Status", ["Todos", "Processado", "Erro"])
    with col3:
        filtro_evento = st.text_input("Filtrar evento", placeholder="ex: agendamento")

    if st.button("Atualizar", type="primary"):
        st.rerun()

    # Consulta
    data_ini = datetime.now() - timedelta(days=periodo)
    conditions = ["tenant_id = %s", "criado_em >= %s"]
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

    st.caption(f"{len(rows)} evento(s) encontrado(s)")
    st.divider()

    for row in rows:
        log_id, evento, processado, erro, criado_em, payload_raw = row

        icone = "✅" if processado and not erro else "❌"
        ts = criado_em.strftime("%d/%m %H:%M:%S") if criado_em else "—"
        label = f"{icone} `{evento}` — {ts}"

        with st.expander(label, expanded=bool(erro)):
            c1, c2 = st.columns(2)
            c1.write(f"**ID:** {log_id}")
            c2.write(f"**Status:** {'OK' if processado and not erro else ('Erro' if erro else 'Não processado')}")

            if erro:
                st.error(f"Erro: {erro}")

            st.markdown("**Payload recebido:**")
            if payload_raw:
                try:
                    data = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
                    st.json(data)
                except Exception:
                    st.code(str(payload_raw))
            else:
                st.caption("Payload vazio")
