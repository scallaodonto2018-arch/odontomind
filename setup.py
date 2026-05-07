"""
OdontoMind — Setup inicial
Cria o tenant Scalla Odonto e o usuário master.

Uso:
    python setup.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_conn
from auth import hash_senha


def setup(
    tenant_id: str = "scalla-odonto",
    tenant_nome: str = "Scalla Odonto",
    admin_username: str = "eduardo",
    admin_nome: str = "Eduardo",
    admin_senha: str = None,
    admin_email: str = "esds1970@gmail.com",
):
    print("Inicializando schema...")
    init_db()

    if not admin_senha:
        import getpass
        admin_senha = getpass.getpass(f"Senha para o usuário '{admin_username}': ")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Tenant
            cur.execute("""
                INSERT INTO tenants (id, nome, slug, ativo, plano)
                VALUES (%s, %s, %s, TRUE, 'professional')
                ON CONFLICT (id) DO UPDATE SET nome=EXCLUDED.nome
            """, (tenant_id, tenant_nome, tenant_id))

            # Usuário master
            cur.execute("""
                INSERT INTO usuarios (tenant_id, username, nome, email, senha_hash, papel, funcao)
                VALUES (%s, %s, %s, %s, %s, 'master', 'gerente_admin')
                ON CONFLICT (tenant_id, username) DO UPDATE SET
                    nome=EXCLUDED.nome,
                    email=EXCLUDED.email,
                    senha_hash=EXCLUDED.senha_hash,
                    papel='master'
            """, (tenant_id, admin_username, admin_nome, admin_email, hash_senha(admin_senha)))

    print(f"\nSetup concluído!")
    print(f"  Tenant:  {tenant_id} ({tenant_nome})")
    print(f"  Usuário: {admin_username} (master)")
    print(f"\nInicie o frontend: streamlit run app.py")
    print(f"Inicie o backend:  uvicorn backend:app --port 8000")


if __name__ == "__main__":
    setup()
