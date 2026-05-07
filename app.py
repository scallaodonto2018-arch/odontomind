"""OdontoMind — Frontend Streamlit."""
import streamlit as st

st.set_page_config(
    page_title="OdontoMind",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

from auth import login_page, logout, require_auth
from pages import pacientes, pipeline, importacao, configuracoes, webhook_logs


def main():
    # Login
    if not st.session_state.get("usuario"):
        login_page()
        return

    usuario = st.session_state.usuario

    # Sidebar
    with st.sidebar:
        st.markdown("## 🦷 OdontoMind")
        st.caption(usuario.get("tenant_nome", ""))
        st.divider()

        opcoes = ["Pipeline", "Pacientes", "Importação", "Configurações"]
        if usuario.get("papel") in ("master", "admin"):
            opcoes.append("Webhook Logs")

        pagina = st.radio(
            "Navegação",
            opcoes,
            label_visibility="collapsed",
        )

        st.divider()
        st.caption(f"Olá, **{usuario['nome']}**")
        if st.button("Sair", use_container_width=True):
            logout()

    # Roteamento
    if pagina == "Pipeline":
        pipeline.show()
    elif pagina == "Pacientes":
        pacientes.show()
    elif pagina == "Importação":
        importacao.show()
    elif pagina == "Configurações":
        if usuario.get("papel") in ("master", "admin"):
            configuracoes.show()
        else:
            st.error("Acesso restrito a administradores.")
    elif pagina == "Webhook Logs":
        webhook_logs.show()


if __name__ == "__main__":
    main()
