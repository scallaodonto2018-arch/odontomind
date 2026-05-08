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

_NAV_ICONS = {
    "Pipeline": "📊",
    "Pacientes": "👥",
    "Importação": "📥",
    "Configurações": "⚙️",
    "Webhook Logs": "🔗",
}


def _injetar_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

*, html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Background ─────────────────────── */
.stApp, [data-testid="stMain"] {
    background-color: #F9FAFB;
}
[data-testid="stMain"] > div { padding-top: 1.25rem; }

/* ── Sidebar ─────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E5E7EB;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0; }

/* ── Nav radio ───────────────────────── */
[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap: 0.125rem !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: 0.5rem 0.75rem !important;
    border-radius: 0.5rem !important;
    cursor: pointer;
    color: #374151 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: background-color 0.12s;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background-color: #F3F4F6 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label[aria-checked="true"] {
    background-color: #DBEAFE !important;
    color: #1E40AF !important;
    font-weight: 600 !important;
}

/* ── Metrics ──────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB !important;
    border-radius: 0.75rem;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    color: #6B7280 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    color: #111827 !important;
}

/* ── Cards / Bordered containers ──────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 0.75rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}

/* ── Tabs ─────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background-color: #F3F4F6;
    border-radius: 0.625rem;
    padding: 0.2rem;
    gap: 0.1rem;
    border-bottom: none !important;
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent !important;
    border-radius: 0.5rem !important;
    border: none !important;
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: #6B7280 !important;
    padding: 0.35rem 0.85rem !important;
}
.stTabs [aria-selected="true"] {
    background-color: #FFFFFF !important;
    color: #1E40AF !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
    font-weight: 600 !important;
}

/* ── Buttons ──────────────────────────── */
button[kind="primary"] {
    background-color: #1E40AF !important;
    border-color: #1E40AF !important;
    border-radius: 0.5rem !important;
    font-size: 0.875rem !important;
    font-weight: 600 !important;
}
button[kind="primary"]:hover {
    background-color: #1D3D99 !important;
    border-color: #1D3D99 !important;
}
button[kind="secondary"], button[kind=""] {
    border-radius: 0.5rem !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
}

/* ── Expanders ────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #E5E7EB !important;
    border-radius: 0.75rem !important;
    background-color: #FFFFFF !important;
}

/* ── Headings ─────────────────────────── */
h1 { font-size: 1.45rem !important; font-weight: 700 !important; color: #111827 !important; margin-bottom: 0.75rem !important; }
h2 { font-size: 1.1rem !important; font-weight: 600 !important; color: #1F2937 !important; }
h3 { font-size: 0.975rem !important; font-weight: 600 !important; color: #374151 !important; }

/* ── Inputs ───────────────────────────── */
.stTextInput > div > div > input,
.stSelectbox > div > div {
    border-radius: 0.5rem !important;
    border-color: #E5E7EB !important;
    font-size: 0.875rem !important;
}

/* ── Caption ──────────────────────────── */
[data-testid="stCaptionContainer"] p {
    color: #6B7280 !important;
    font-size: 0.8rem !important;
}

/* ── Alerts ───────────────────────────── */
[data-testid="stAlert"] { border-radius: 0.625rem !important; }

/* ── Divider ──────────────────────────── */
hr { border-color: #F3F4F6 !important; margin: 0.5rem 0 !important; }

/* ──────────────────────────────────────
   Badge / pill system
   Usage: <span class="om-badge om-green">Ativo</span>
   ────────────────────────────────────── */
.om-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.15rem 0.55rem;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 600;
    line-height: 1.4;
    white-space: nowrap;
    vertical-align: middle;
}
.om-blue   { background: #DBEAFE; color: #1E40AF; }
.om-yellow { background: #FEF3C7; color: #92400E; }
.om-orange { background: #FFEDD5; color: #9A3412; }
.om-purple { background: #EDE9FE; color: #5B21B6; }
.om-indigo { background: #E0E7FF; color: #3730A3; }
.om-teal   { background: #CCFBF1; color: #134E4A; }
.om-green  { background: #D1FAE5; color: #065F46; }
.om-red    { background: #FEE2E2; color: #991B1B; }
.om-gray   { background: #F3F4F6; color: #374151; }
</style>
""", unsafe_allow_html=True)


def main():
    _injetar_css()

    if not st.session_state.get("usuario"):
        login_page()
        return

    usuario = st.session_state.usuario

    with st.sidebar:
        st.markdown(f"""
<div style="padding:1.25rem 0.75rem 0.75rem;">
  <div style="font-size:1.15rem;font-weight:700;color:#1E40AF;letter-spacing:-0.01em;">
    🦷 OdontoMind
  </div>
  <div style="font-size:0.75rem;color:#9CA3AF;margin-top:0.15rem;">
    {usuario.get("tenant_nome", "")}
  </div>
</div>
<hr style="margin:0 0 0.75rem;border-color:#F3F4F6;">
""", unsafe_allow_html=True)

        opcoes_raw = ["Pipeline", "Pacientes", "Importação", "Configurações"]
        if usuario.get("papel") in ("master", "admin"):
            opcoes_raw.append("Webhook Logs")

        opcoes = [f"{_NAV_ICONS.get(o, '')}  {o}" for o in opcoes_raw]
        pagina_display = st.radio("Navegação", opcoes, label_visibility="collapsed")
        pagina = pagina_display.split("  ", 1)[1] if "  " in pagina_display else pagina_display

        st.divider()
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(f"""
<div style="font-size:0.8rem;padding:0.25rem 0;">
  <div style="font-weight:600;color:#374151;">{usuario["nome"]}</div>
  <div style="color:#9CA3AF;font-size:0.72rem;">{usuario.get("funcao", "")}</div>
</div>
""", unsafe_allow_html=True)
        with c2:
            if st.button("Sair", use_container_width=True):
                logout()

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
