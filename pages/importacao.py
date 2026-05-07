"""Página de importação de planilhas do Controle Odonto."""
import os
import tempfile
import streamlit as st

from auth import require_papel
from importers import runner as imp_runner
from importers import gerar_oportunidades as imp_oport


def show():
    usuario = require_papel(["master", "admin"])
    tenant_id = usuario["tenant_id"]

    st.title("Importar Planilhas")
    st.caption("Carregue as planilhas exportadas do Controle Odonto para sincronizar a base de dados.")

    st.info(
        "**Ordem recomendada:** Pacientes primeiro (cria a base), depois Orçamentos, Contratos e Procedimentos.\n\n"
        "Pode importar apenas um tipo de cada vez ou todos de uma vez.",
        icon="ℹ️",
    )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        f_pacientes = st.file_uploader(
            "Pacientes (`ControleODONTO - Pacientes.xlsx`)",
            type=["xlsx"], key="up_pac",
        )
        f_contratos = st.file_uploader(
            "Contratos (`Contratos.xlsx`)",
            type=["xlsx"], key="up_con",
        )
    with col2:
        f_orcamentos = st.file_uploader(
            "Orçamentos (`Orçamentos Emitidos.xlsx`)",
            type=["xlsx"], key="up_orc",
        )
        f_procedimentos = st.file_uploader(
            "Procedimentos (`Procedimentos Realizados.xlsx`)",
            type=["xlsx"], key="up_proc",
        )

    arquivos = {
        "pacientes": f_pacientes,
        "orcamentos": f_orcamentos,
        "contratos": f_contratos,
        "procedimentos": f_procedimentos,
    }
    tem_arquivo = any(v is not None for v in arquivos.values())

    if not tem_arquivo:
        st.caption("Nenhum arquivo selecionado.")
        return

    nomes = [k for k, v in arquivos.items() if v]
    st.write(f"Pronto para importar: **{', '.join(nomes)}**")

    if not st.button("Importar", type="primary", use_container_width=False):
        return

    # Salva arquivos temporariamente e chama importadores
    tmp_dir = tempfile.mkdtemp()
    caminhos = {}
    for chave, f in arquivos.items():
        if f:
            path = os.path.join(tmp_dir, f.name)
            with open(path, "wb") as fp:
                fp.write(f.getvalue())
            caminhos[chave] = path

    st.divider()
    resultados = {}

    importadores = {
        "pacientes": ("Pacientes", imp_runner.imp_pac.importar),
        "orcamentos": ("Orçamentos", imp_runner.imp_orc.importar),
        "contratos": ("Contratos", imp_runner.imp_con.importar),
        "procedimentos": ("Procedimentos", imp_runner.imp_proc.importar),
    }

    for chave, (label, fn) in importadores.items():
        if chave not in caminhos:
            continue

        with st.spinner(f"Importando {label}..."):
            try:
                res = fn(tenant_id, caminhos[chave])
                resultados[chave] = res
            except Exception as e:
                st.error(f"Erro ao importar {label}: {e}")
                resultados[chave] = {"erro_fatal": str(e)}

    # Passo 5: gerar oportunidades históricas
    with st.spinner("Gerando oportunidades históricas..."):
        try:
            res_oport = imp_oport.gerar(tenant_id)
            resultados["oportunidades"] = res_oport
        except Exception as e:
            resultados["oportunidades"] = {"erro_fatal": str(e)}

    st.divider()
    st.subheader("Resultado")

    labels = {
        "pacientes": "Pacientes",
        "orcamentos": "Orçamentos",
        "contratos": "Contratos",
        "procedimentos": "Procedimentos",
        "oportunidades": "Oportunidades geradas",
    }
    for chave, res in resultados.items():
        label = labels.get(chave, chave.capitalize())
        if "erro_fatal" in res:
            st.error(f"**{label}:** {res['erro_fatal']}")
        elif chave == "oportunidades":
            criadas = res.get("criadas", 0)
            total = res.get("total", 0)
            st.success(f"**{label}** — {criadas} criadas de {total} tratamentos")
        else:
            inseridos = res.get("inseridos", 0)
            atualizados = res.get("atualizados", 0)
            erros = res.get("erros", 0)
            sem_pac = res.get("sem_paciente", 0)
            total = res.get("total", inseridos + atualizados + erros)

            partes = [f"Total: {total}", f"Novos: {inseridos}", f"Atualizados: {atualizados}"]
            if erros:
                partes.append(f"Erros: {erros}")
            if sem_pac:
                partes.append(f"Sem paciente: {sem_pac}")

            if erros:
                st.warning(f"**{label}** — " + " | ".join(partes))
            else:
                st.success(f"**{label}** — " + " | ".join(partes))

    # Limpa arquivos temporários
    for path in caminhos.values():
        try:
            os.remove(path)
        except Exception:
            pass
    try:
        os.rmdir(tmp_dir)
    except Exception:
        pass
