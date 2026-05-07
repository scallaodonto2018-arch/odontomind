"""Autenticação DB-based para o OdontoMind."""
import bcrypt
import streamlit as st
from database import get_conn


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def verificar_senha(senha: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode(), hash_.encode())
    except Exception:
        return False


def verificar_login(username: str, senha: str) -> dict | None:
    """Retorna dict com dados do usuário ou None se inválido."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.id, u.nome, u.email, u.senha_hash, u.papel, u.funcao, u.tenant_id,
                           t.nome as tenant_nome, t.co_usuario, t.co_senha, t.co_estab_id
                    FROM usuarios u
                    JOIN tenants t ON t.id = u.tenant_id
                    WHERE u.username = %s AND u.ativo = TRUE AND t.ativo = TRUE
                """, (username,))
                row = cur.fetchone()
        if not row:
            return None
        uid, nome, email, senha_hash, papel, funcao, tenant_id, tenant_nome, co_usuario, co_senha, co_estab_id = row
        if not verificar_senha(senha, senha_hash):
            return None
        return {
            "id": uid,
            "username": username,
            "nome": nome,
            "email": email,
            "papel": papel,
            "funcao": funcao,
            "tenant_id": tenant_id,
            "tenant_nome": tenant_nome,
            "co_usuario": co_usuario,
            "co_senha": co_senha,
            "co_estab_id": co_estab_id,
        }
    except Exception as e:
        st.error(f"Erro ao conectar ao banco: {e}")
        return None


def criar_usuario(tenant_id: str, username: str, nome: str, senha: str,
                  papel: str = "user", funcao: str = None, email: str = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO usuarios (tenant_id, username, nome, email, senha_hash, papel, funcao)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, username) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    email = EXCLUDED.email,
                    senha_hash = EXCLUDED.senha_hash,
                    papel = EXCLUDED.papel,
                    funcao = EXCLUDED.funcao
            """, (tenant_id, username, nome, email, hash_senha(senha), papel, funcao))


# ----------------------------------------------------------------
# Streamlit helpers
# ----------------------------------------------------------------

def login_page():
    """Renderiza a página de login. Retorna True se autenticado."""
    if st.session_state.get("usuario"):
        return True

    st.markdown("## OdontoMind")
    st.markdown("##### O cérebro da odontologia")
    st.divider()

    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if entrar:
        if not usuario or not senha:
            st.error("Preencha usuário e senha.")
            return False
        dados = verificar_login(usuario, senha)
        if dados:
            st.session_state.usuario = dados
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")

    return False


def require_auth():
    """Bloqueia página se não autenticado. Retorna dados do usuário."""
    if not st.session_state.get("usuario"):
        st.warning("Faça login para acessar esta página.")
        st.stop()
    return st.session_state.usuario


def require_papel(papeis: list[str]):
    """Bloqueia página se o papel do usuário não for permitido."""
    usuario = require_auth()
    if usuario["papel"] not in papeis:
        st.error("Acesso negado.")
        st.stop()
    return usuario


def logout():
    st.session_state.pop("usuario", None)
    st.rerun()
