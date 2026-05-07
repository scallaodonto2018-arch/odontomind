"""
CLI para importação completa das planilhas do Controle Odonto.

Uso:
    python -m importers.runner --tenant scalla-odonto --pasta "C:/caminho/planilhas"

Ou com arquivos individuais:
    python -m importers.runner --tenant scalla-odonto \
        --pacientes "Pacientes.xlsx" \
        --orcamentos "Orcamentos.xlsx" \
        --contratos "Contratos.xlsx" \
        --procedimentos "Procedimentos.xlsx"
"""
import sys
import os
import argparse
import glob as _glob

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import init_db
from importers import pacientes as imp_pac
from importers import orcamentos as imp_orc
from importers import contratos as imp_con
from importers import procedimentos as imp_proc
from importers import gerar_oportunidades as imp_oport


def _encontrar_arquivo(pasta: str, padrao: str) -> str | None:
    """Procura arquivo na pasta usando glob case-insensitive."""
    matches = _glob.glob(os.path.join(pasta, f"*{padrao}*"))
    return matches[0] if matches else None


def _progresso(atual, total):
    pct = int(atual / total * 100) if total else 0
    print(f"\r  {atual}/{total} ({pct}%)", end="", flush=True)


def rodar(
    tenant_id: str,
    arquivo_pacientes: str = None,
    arquivo_orcamentos: str = None,
    arquivo_contratos: str = None,
    arquivo_procedimentos: str = None,
    pasta: str = None,
    verbose: bool = True,
) -> dict:
    """
    Roda todos os importadores disponíveis.
    Retorna dict com resultados de cada importação.
    """
    resultados = {}

    def _log(msg):
        if verbose:
            print(msg)

    # Resolve caminhos pela pasta se arquivos individuais não informados
    if pasta:
        arquivo_pacientes = arquivo_pacientes or _encontrar_arquivo(pasta, "Pacientes")
        arquivo_orcamentos = arquivo_orcamentos or _encontrar_arquivo(pasta, "Orcamentos") or _encontrar_arquivo(pasta, "Orçamentos")
        arquivo_contratos = arquivo_contratos or _encontrar_arquivo(pasta, "Contratos")
        arquivo_procedimentos = arquivo_procedimentos or _encontrar_arquivo(pasta, "Procedimentos")

    # 1. Pacientes (deve ser o primeiro — cria a base de pacientes)
    if arquivo_pacientes and os.path.exists(arquivo_pacientes):
        _log(f"\n[1/4] Importando pacientes: {os.path.basename(arquivo_pacientes)}")
        res = imp_pac.importar(tenant_id, arquivo_pacientes, callback=_progresso if verbose else None)
        print()
        _log(f"      Inseridos: {res['inseridos']} | Atualizados: {res['atualizados']} | Erros: {res['erros']}")
        resultados["pacientes"] = res
    else:
        _log("[1/4] Planilha de pacientes não encontrada — pulando.")

    # 2. Orçamentos
    if arquivo_orcamentos and os.path.exists(arquivo_orcamentos):
        _log(f"\n[2/4] Importando orçamentos: {os.path.basename(arquivo_orcamentos)}")
        res = imp_orc.importar(tenant_id, arquivo_orcamentos, callback=_progresso if verbose else None)
        print()
        _log(f"      Inseridos: {res['inseridos']} | Atualizados: {res['atualizados']} | Erros: {res['erros']} | Sem paciente: {res['sem_paciente']}")
        resultados["orcamentos"] = res
    else:
        _log("[2/4] Planilha de orçamentos não encontrada — pulando.")

    # 3. Contratos
    if arquivo_contratos and os.path.exists(arquivo_contratos):
        _log(f"\n[3/4] Importando contratos: {os.path.basename(arquivo_contratos)}")
        res = imp_con.importar(tenant_id, arquivo_contratos, callback=_progresso if verbose else None)
        print()
        _log(f"      Inseridos: {res['inseridos']} | Atualizados: {res['atualizados']} | Erros: {res['erros']} | Sem paciente: {res['sem_paciente']}")
        resultados["contratos"] = res
    else:
        _log("[3/4] Planilha de contratos não encontrada — pulando.")

    # 4. Procedimentos
    if arquivo_procedimentos and os.path.exists(arquivo_procedimentos):
        _log(f"\n[4/4] Importando procedimentos: {os.path.basename(arquivo_procedimentos)}")
        res = imp_proc.importar(tenant_id, arquivo_procedimentos, callback=_progresso if verbose else None)
        print()
        _log(f"      Inseridos: {res['inseridos']} | Erros: {res['erros']} | Sem paciente: {res['sem_paciente']}")
        resultados["procedimentos"] = res
    else:
        _log("[4/4] Planilha de procedimentos não encontrada — pulando.")

    # 5. Gerar oportunidades históricas
    _log("\n[5/5] Gerando oportunidades históricas a partir dos tratamentos...")
    res = imp_oport.gerar(tenant_id)
    _log(f"      Criadas: {res['criadas']} de {res['total']} tratamentos")
    resultados["oportunidades"] = res

    return resultados


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OdontoMind — importador de planilhas CO")
    parser.add_argument("--tenant", required=True, help="ID do tenant (ex: scalla-odonto)")
    parser.add_argument("--pasta", help="Pasta com as planilhas")
    parser.add_argument("--pacientes", help="Caminho da planilha de pacientes")
    parser.add_argument("--orcamentos", help="Caminho da planilha de orçamentos")
    parser.add_argument("--contratos", help="Caminho da planilha de contratos")
    parser.add_argument("--procedimentos", help="Caminho da planilha de procedimentos")
    parser.add_argument("--init-db", action="store_true", help="Inicializa o schema antes de importar")
    args = parser.parse_args()

    if args.init_db:
        print("Inicializando schema...")
        init_db()

    rodar(
        tenant_id=args.tenant,
        arquivo_pacientes=args.pacientes,
        arquivo_orcamentos=args.orcamentos,
        arquivo_contratos=args.contratos,
        arquivo_procedimentos=args.procedimentos,
        pasta=args.pasta,
    )
    print("\nImportação concluída.")
