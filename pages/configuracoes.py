"""Página de configurações — tenant, credenciais CO e usuários."""
import streamlit as st
from auth import require_papel, criar_usuario, hash_senha
from database import get_conn
from co_api import ControleOdontoAPI


def _get_tenant(tenant_id: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, co_usuario, co_senha, co_estab_id FROM tenants WHERE id=%s",
                (tenant_id,),
            )
            row = cur.fetchone()
    if not row:
        return {}
    return {"id": row[0], "nome": row[1], "co_usuario": row[2], "co_senha": row[3], "co_estab_id": row[4]}


def _salvar_tenant(tenant_id: str, nome: str, co_usuario: str, co_senha: str, co_estab_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE tenants SET nome=%s, co_usuario=%s, co_senha=%s, co_estab_id=%s
                WHERE id=%s
            """, (nome, co_usuario or None, co_senha or None, co_estab_id or None, tenant_id))


def _listar_usuarios(tenant_id: str) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, nome, email, papel, funcao, ativo
                FROM usuarios WHERE tenant_id=%s ORDER BY nome
            """, (tenant_id,))
            cols = ["id","username","nome","email","papel","funcao","ativo"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def _ativar_desativar_usuario(usuario_id: int, ativo: bool):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET ativo=%s WHERE id=%s", (ativo, usuario_id))


def _alterar_senha(usuario_id: int, nova_senha: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET senha_hash=%s WHERE id=%s", (hash_senha(nova_senha), usuario_id))


def show():
    usuario = require_papel(["master", "admin"])
    tenant_id = usuario["tenant_id"]

    st.title("Configurações")

    tab_clinica, tab_co, tab_usuarios = st.tabs(["Clínica", "Controle Odonto", "Usuários"])

    # ----------------------------------------------------------------
    # Aba: Clínica
    # ----------------------------------------------------------------
    with tab_clinica:
        tenant = _get_tenant(tenant_id)
        st.subheader("Dados da clínica")

        with st.form("form_clinica"):
            nome = st.text_input("Nome da clínica", value=tenant.get("nome", ""))
            salvar = st.form_submit_button("Salvar", type="primary")

        if salvar:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE tenants SET nome=%s WHERE id=%s", (nome, tenant_id))
            st.success("Salvo!")
            st.session_state.usuario["tenant_nome"] = nome
            st.rerun()

    # ----------------------------------------------------------------
    # Aba: Controle Odonto
    # ----------------------------------------------------------------
    with tab_co:
        tenant = _get_tenant(tenant_id)
        st.subheader("Credenciais Controle Odonto")
        st.caption("Usadas para sincronização via API e para validar webhooks.")

        with st.form("form_co"):
            co_usuario = st.text_input("Usuário CO", value=tenant.get("co_usuario") or "")
            co_senha = st.text_input("Senha CO", type="password",
                                     value=tenant.get("co_senha") or "",
                                     help="Deixe em branco para manter a senha atual")
            co_estab_id = st.text_input("Estabelecimento ID", value=tenant.get("co_estab_id") or "",
                                        help="Deixe em branco para detectar automaticamente via JWT")
            salvar_co = st.form_submit_button("Salvar credenciais", type="primary")

        if salvar_co:
            # Não sobrescreve senha se campo vazio
            senha_final = co_senha if co_senha else tenant.get("co_senha") or ""
            _salvar_tenant(tenant_id, tenant.get("nome", ""), co_usuario, senha_final, co_estab_id)
            st.success("Credenciais salvas!")
            st.rerun()

        st.divider()
        st.subheader("Testar conexão")
        if st.button("Testar conexão CO"):
            tenant_atual = _get_tenant(tenant_id)
            if not tenant_atual.get("co_usuario") or not tenant_atual.get("co_senha"):
                st.error("Configure usuário e senha primeiro.")
            else:
                try:
                    api = ControleOdontoAPI(
                        usuario=tenant_atual["co_usuario"],
                        senha=tenant_atual["co_senha"],
                        estabelecimento_id=tenant_atual.get("co_estab_id") or None,
                    )
                    api.autenticar()
                    st.success(f"Conectado! Estabelecimento ID: {api.estabelecimento_id}")
                    if not tenant_atual.get("co_estab_id"):
                        _salvar_tenant(
                            tenant_id, tenant_atual["nome"],
                            tenant_atual["co_usuario"], tenant_atual["co_senha"],
                            api.estabelecimento_id,
                        )
                        st.info("Estabelecimento ID salvo automaticamente.")
                except Exception as e:
                    st.error(f"Erro: {e}")

        st.divider()
        st.subheader("URL do webhook")
        st.caption(
            "Configure esta URL no painel Controle Odonto → Configurações → Webhooks:"
        )
        st.code(f"https://SEU-DOMINIO.railway.app/webhook/{tenant_id}/controle-odonto")
        st.caption(
            "Eventos a ativar: Cadastro/Alteração/Cancelamento de Agendamento, "
            "Paciente Faltar, Confirmou Agendamento, Cadastro de Orçamento, "
            "Orçamento Aprovado, Cancelamento de Orçamento, Início do Atendimento, "
            "Cadastro do Paciente"
        )

    # ----------------------------------------------------------------
    # Aba: Usuários
    # ----------------------------------------------------------------
    with tab_usuarios:
        st.subheader("Usuários")

        usuarios = _listar_usuarios(tenant_id)

        for u in usuarios:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                c1.write(f"**{u['nome']}** (`{u['username']}`)")
                c2.caption(u.get("papel") or "—")
                c3.caption(u.get("funcao") or "—")
                ativo_txt = "Ativo" if u["ativo"] else "Inativo"
                c4.caption(ativo_txt)
                if c5.button("Desativar" if u["ativo"] else "Ativar", key=f"tog_{u['id']}"):
                    _ativar_desativar_usuario(u["id"], not u["ativo"])
                    st.rerun()

        st.divider()
        st.subheader("Adicionar usuário")

        FUNCOES = {
            "crc_leads": "CRC Leads",
            "crc_comercial": "CRC Comercial",
            "crc_marketing": "CRC Marketing",
            "gerente_admin": "Gerente Admin",
            "dentista": "Dentista",
            "aux_admin": "Aux. Administrativo",
            "master": "Master",
        }

        with st.form("form_novo_usuario"):
            col_a, col_b = st.columns(2)
            novo_username = col_a.text_input("Usuário (login)")
            novo_nome = col_b.text_input("Nome completo")
            novo_email = col_a.text_input("Email (opcional)")
            novo_papel = col_b.selectbox("Papel", ["user", "admin", "master"])
            nova_funcao = col_a.selectbox("Função", list(FUNCOES.keys()),
                                          format_func=lambda k: FUNCOES[k])
            nova_senha = col_b.text_input("Senha", type="password")
            criar = st.form_submit_button("Criar usuário", type="primary")

        if criar:
            if not novo_username or not novo_nome or not nova_senha:
                st.error("Usuário, nome e senha são obrigatórios.")
            else:
                try:
                    criar_usuario(
                        tenant_id=tenant_id,
                        username=novo_username,
                        nome=novo_nome,
                        senha=nova_senha,
                        papel=novo_papel,
                        funcao=nova_funcao,
                        email=novo_email or None,
                    )
                    st.success(f"Usuário '{novo_username}' criado!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
