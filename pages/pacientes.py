"""Página de pacientes — busca, filtros e perfil."""
import streamlit as st
from auth import require_auth
from database import get_conn

STATUS_COR = {
    "ativo":      "green",
    "inativo":    "red",
    "prospect":   "yellow",
    "reativacao": "teal",
}

OPORT_COR = {
    "lead_novo": "blue", "contato_feito": "yellow", "agendado": "orange",
    "compareceu": "purple", "orcamento_enviado": "indigo", "negociando": "teal",
    "fechado_ganho": "green", "fechado_perdido": "red",
}

OPORT_LABELS = {
    "lead_novo": "Lead Novo", "contato_feito": "Contato Feito", "agendado": "Agendado",
    "compareceu": "Compareceu", "orcamento_enviado": "Orç. Enviado", "negociando": "Negociando",
    "fechado_ganho": "Fechado ✓", "fechado_perdido": "Perdido",
}


def _badge(texto: str, cor: str = "gray") -> str:
    return f'<span class="om-badge om-{cor}">{texto}</span>'


def _buscar_pacientes(tenant_id: str, busca: str, status: str, captacao: str,
                      limit: int, offset: int) -> tuple[list, int]:
    conditions = ["p.tenant_id = %s"]
    params = [tenant_id]

    if busca:
        conditions.append("(p.nome ILIKE %s OR p.whatsapp ILIKE %s OR p.email ILIKE %s)")
        like = f"%{busca}%"
        params.extend([like, like, like])

    if status and status != "Todos":
        conditions.append("p.status = %s")
        params.append(status)

    if captacao and captacao != "Todos":
        conditions.append("p.captacao = %s")
        params.append(captacao)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM pacientes p WHERE {where}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT p.id, p.nome, p.whatsapp, p.email,
                       p.captacao, p.ultima_consulta, p.data_cadastro,
                       p.status, p.balanca_financeira,
                       (SELECT COUNT(*) FROM oportunidades o WHERE o.paciente_id=p.id) as n_oport,
                       (SELECT COUNT(*) FROM tratamentos t WHERE t.paciente_id=p.id) as n_trat
                FROM pacientes p
                WHERE {where}
                ORDER BY p.nome
                LIMIT %s OFFSET %s
            """, params + [limit, offset])

            cols = ["id","nome","whatsapp","email","captacao","ultima_consulta",
                    "data_cadastro","status","balanca_financeira","n_oport","n_trat"]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    return rows, total


def _perfil_paciente(tenant_id: str, paciente_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT nome, cpf, whatsapp, telefone, email,
                       data_nascimento, data_cadastro, ultima_consulta,
                       captacao, balanca_financeira, status, prontuario_id
                FROM pacientes WHERE id=%s AND tenant_id=%s
            """, (paciente_id, tenant_id))
            row = cur.fetchone()
            if not row:
                st.warning("Paciente não encontrado.")
                return
            nome, cpf, whatsapp, telefone, email, \
                nascimento, cadastro, ultima, captacao, \
                balanca, status, prontuario = row

            st.subheader(nome)

            c1, c2, c3 = st.columns(3)
            c1.metric("Prontuário", prontuario or "—")
            c2.metric("Status", status or "ativo")
            c3.metric("Saldo", f"R$ {balanca:,.2f}" if balanca else "R$ 0,00")

            with st.expander("Dados de contato"):
                if whatsapp:
                    st.write(f"WhatsApp: `{whatsapp}`")
                if telefone:
                    st.write(f"Telefone: `{telefone}`")
                if email:
                    st.write(f"Email: {email}")
                if nascimento:
                    st.write(f"Nascimento: {nascimento.strftime('%d/%m/%Y')}")
                if captacao:
                    st.write(f"Captação: {captacao}")

            # Oportunidades
            cur.execute("""
                SELECT status, origem, crc_responsavel, valor_orcado, valor_fechado,
                       data_entrada, data_ultima_atividade, observacoes
                FROM oportunidades WHERE paciente_id=%s AND tenant_id=%s
                ORDER BY data_entrada DESC
            """, (paciente_id, tenant_id))
            oports = cur.fetchall()

            if oports:
                with st.expander(f"Oportunidades ({len(oports)})", expanded=True):
                    for o in oports:
                        status_op, origem, crc, v_orc, v_fec, dt_ent, dt_ult, obs = o
                        cor = OPORT_COR.get(status_op, "gray")
                        label = OPORT_LABELS.get(status_op, status_op)
                        st.markdown(
                            f'{_badge(label, cor)}'
                            f'&nbsp;<span style="font-size:0.8rem;color:#6B7280;">{origem or "—"}</span>',
                            unsafe_allow_html=True,
                        )
                        if crc:
                            st.caption(f"CRC: {crc}")
                        col_a, col_b = st.columns(2)
                        if v_orc:
                            col_a.caption(f"Orçado: R$ {v_orc:,.2f}")
                        if v_fec:
                            col_b.caption(f"Fechado: R$ {v_fec:,.2f}")
                        if dt_ent:
                            st.caption(
                                f"Entrada: {dt_ent.strftime('%d/%m/%Y') if hasattr(dt_ent,'strftime') else str(dt_ent)[:10]}"
                            )
                        st.divider()

            # Tratamentos
            cur.execute("""
                SELECT tipo, situacao, dentista, vendedor,
                       valor_total, data_emissao, data_aprovacao, campanha_marketing
                FROM tratamentos WHERE paciente_id=%s AND tenant_id=%s
                ORDER BY data_emissao DESC
            """, (paciente_id, tenant_id))
            tratas = cur.fetchall()

            if tratas:
                with st.expander(f"Tratamentos/Orçamentos ({len(tratas)})"):
                    for t in tratas:
                        tipo, sit, dentista, vendedor, valor, d_em, d_ap, campanha = t
                        label = "Contrato" if tipo == "contrato" else "Orçamento"
                        cor_t = "green" if tipo == "contrato" else "indigo"
                        st.markdown(
                            f'{_badge(label, cor_t)}'
                            f'&nbsp;<span style="font-size:0.8rem;color:#374151;">{sit or "—"}</span>',
                            unsafe_allow_html=True,
                        )
                        if valor:
                            st.caption(f"R$ {valor:,.2f}")
                        if d_em:
                            st.caption(f"Emissão: {d_em.strftime('%d/%m/%Y') if d_em else '—'}")
                        if d_ap:
                            st.caption(f"Aprovação: {d_ap.strftime('%d/%m/%Y') if d_ap else '—'}")
                        if dentista:
                            st.caption(f"Dentista: {dentista}")
                        if vendedor:
                            st.caption(f"Vendedor: {vendedor}")
                        st.divider()

            # Procedimentos
            cur.execute("""
                SELECT data_realizacao, especialidade, nome_procedimento,
                       dentista, valor, situacao
                FROM procedimentos WHERE paciente_id=%s AND tenant_id=%s
                ORDER BY data_realizacao DESC LIMIT 20
            """, (paciente_id, tenant_id))
            procs = cur.fetchall()

            if procs:
                with st.expander(f"Procedimentos realizados ({len(procs)})"):
                    for p in procs:
                        d, espec, nome_p, dent, val, sit = p
                        dt_str = d.strftime('%d/%m/%Y') if d else "—"
                        st.markdown(f"**{dt_str}** — {nome_p or '—'}")
                        st.caption(
                            f"{espec or ''}{' | ' if espec and dent else ''}{dent or ''}"
                            f"{' | ' if (espec or dent) and val else ''}{f'R$ {val:,.2f}' if val else ''}"
                        )


def show():
    usuario = require_auth()
    tenant_id = usuario["tenant_id"]

    st.title("Pacientes")

    # Filtros
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    with col1:
        busca = st.text_input("Buscar", placeholder="Nome, WhatsApp ou email...",
                              label_visibility="collapsed")
    with col2:
        status_filtro = st.selectbox("Status", ["Todos", "ativo", "inativo", "prospect"],
                                     label_visibility="collapsed")
    with col3:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT captacao FROM pacientes WHERE tenant_id=%s AND captacao IS NOT NULL ORDER BY captacao",
                        (tenant_id,),
                    )
                    captacoes = ["Todos"] + [r[0] for r in cur.fetchall()]
        except Exception:
            captacoes = ["Todos"]
        captacao_filtro = st.selectbox("Captação", captacoes, label_visibility="collapsed")
    with col4:
        por_pagina = st.selectbox("Por página", [50, 100, 200], label_visibility="collapsed")

    if "pac_pagina" not in st.session_state:
        st.session_state.pac_pagina = 0

    offset = st.session_state.pac_pagina * por_pagina
    lista, total = _buscar_pacientes(tenant_id, busca, status_filtro,
                                     captacao_filtro, por_pagina, offset)

    st.markdown(
        f'<div style="font-size:0.8rem;color:#9CA3AF;margin-bottom:0.5rem;">'
        f'{total} paciente(s) encontrado(s)</div>',
        unsafe_allow_html=True,
    )

    if not lista:
        st.info("Nenhum paciente encontrado. Importe as planilhas na página Importação.")
        return

    # Cabeçalho da lista
    st.markdown("""
<div style="display:grid;grid-template-columns:3fr 2fr 1fr 1fr 0.6fr;
            gap:0.5rem;padding:0.25rem 0.75rem;
            font-size:0.7rem;font-weight:600;color:#9CA3AF;text-transform:uppercase;
            letter-spacing:0.06em;border-bottom:1px solid #F3F4F6;margin-bottom:0.25rem;">
  <span>PACIENTE</span>
  <span>CONTATO</span>
  <span>CAPTAÇÃO</span>
  <span>ÚLT. CONSULTA</span>
  <span></span>
</div>
""", unsafe_allow_html=True)

    for p in lista:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 0.6])

            status_p = p.get("status") or "ativo"
            cor_p    = STATUS_COR.get(status_p, "gray")
            badge_s  = _badge(status_p.capitalize(), cor_p)

            with c1:
                n_oport = p.get("n_oport", 0)
                n_trat  = p.get("n_trat", 0)
                extras  = []
                if n_oport:
                    extras.append(f"{n_oport} oport.")
                if n_trat:
                    extras.append(f"{n_trat} trat.")
                extras_html = (
                    f'&nbsp;<span style="font-size:0.72rem;color:#9CA3AF;">'
                    f'{" · ".join(extras)}</span>'
                ) if extras else ""
                st.markdown(
                    f'<div style="padding-top:0.15rem;">'
                    f'<span style="font-size:0.9rem;font-weight:600;color:#111827;">{p["nome"]}</span>'
                    f'&nbsp;{badge_s}{extras_html}</div>',
                    unsafe_allow_html=True,
                )

            with c2:
                contato = p["whatsapp"] or p["email"] or "—"
                st.markdown(
                    f'<div style="font-size:0.8rem;color:#6B7280;padding-top:0.25rem;">{contato}</div>',
                    unsafe_allow_html=True,
                )

            with c3:
                capt = p.get("captacao") or "—"
                st.markdown(
                    f'<div style="font-size:0.8rem;color:#6B7280;padding-top:0.25rem;">{capt}</div>',
                    unsafe_allow_html=True,
                )

            with c4:
                ultima = p["ultima_consulta"]
                dt_str = (
                    ultima.strftime("%d/%m/%Y")
                    if hasattr(ultima, "strftime")
                    else (str(ultima)[:10] if ultima else "—")
                )
                st.markdown(
                    f'<div style="font-size:0.8rem;color:#6B7280;padding-top:0.25rem;">{dt_str}</div>',
                    unsafe_allow_html=True,
                )

            with c5:
                if st.button("Ver", key=f"ver_{p['id']}", use_container_width=True):
                    st.session_state.pac_selecionado = p["id"]

    # Paginação
    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.session_state.pac_pagina > 0:
            if st.button("← Anterior"):
                st.session_state.pac_pagina -= 1
                st.rerun()
    with col_info:
        total_pag = max(1, (total - 1) // por_pagina + 1)
        st.markdown(
            f'<div style="text-align:center;font-size:0.8rem;color:#9CA3AF;padding-top:0.4rem;">'
            f'Página {st.session_state.pac_pagina + 1} de {total_pag}</div>',
            unsafe_allow_html=True,
        )
    with col_next:
        if offset + por_pagina < total:
            if st.button("Próxima →"):
                st.session_state.pac_pagina += 1
                st.rerun()

    # Painel lateral do paciente selecionado
    if st.session_state.get("pac_selecionado"):
        with st.sidebar:
            if st.button("✕ Fechar perfil"):
                del st.session_state.pac_selecionado
                st.rerun()
            _perfil_paciente(tenant_id, st.session_state.pac_selecionado)
