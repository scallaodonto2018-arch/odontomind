"""Cliente da API Controle Odonto — multi-tenant."""
import base64
import json
import requests
from datetime import datetime, timedelta, date
import calendar


BASE_URL = "https://api.aplicativo.net"


def _decode_jwt_payload(token: str) -> dict:
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


class ControleOdontoAPI:
    def __init__(self, usuario: str, senha: str, estabelecimento_id: str = None):
        self.usuario = usuario
        self.senha = senha
        self.estabelecimento_id = estabelecimento_id or ""
        self.token: str | None = None
        self.token_expires: datetime | None = None

    def autenticar(self):
        resp = requests.post(
            f"{BASE_URL}/v4/Auth/pm",
            data={"Nome": self.usuario, "Senha": self.senha},
            timeout=15,
        )
        if not resp.ok:
            try:
                detalhe = resp.json()
            except Exception:
                detalhe = resp.text[:500]
            raise ValueError(
                f"Falha na autenticação (HTTP {resp.status_code}).\n"
                f"Resposta: {detalhe}"
            )
        data = resp.json()
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        self.token = (
            payload.get("token")
            or payload.get("access_token")
            or payload.get("Token")
            or payload.get("accessToken")
        )
        if not self.token:
            raise ValueError(f"Token não encontrado na resposta: {data}")
        self.token_expires = datetime.now() + timedelta(minutes=25)

        if not self.estabelecimento_id:
            jwt_data = _decode_jwt_payload(self.token)
            raw_id = jwt_data.get("estabelecimento_id", "")
            self.estabelecimento_id = str(raw_id).split(",")[0].strip()

        return self.token

    def _headers(self):
        if not self.token or datetime.now() >= self.token_expires:
            self.autenticar()
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, url, params=None):
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        if not resp.ok:
            try:
                detalhe = resp.json()
            except Exception:
                detalhe = resp.text[:300]
            raise ValueError(f"HTTP {resp.status_code} em {url}\n{detalhe}")
        if not resp.text.strip():
            return []
        return resp.json()

    @staticmethod
    def _items(data) -> list:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        inner = data.get("data")
        if isinstance(inner, list):
            return inner
        if isinstance(inner, dict):
            candidate = inner.get("items")
            if isinstance(candidate, list):
                return candidate
            return []
        candidate = data.get("items")
        if isinstance(candidate, list):
            return candidate
        return []

    # ----------------------------------------------------------------
    # Agendamentos
    # ----------------------------------------------------------------

    def get_agendamentos(self, data_inicio: str, data_termino: str) -> list:
        """Retorna agendamentos dividindo em fatias de 10 dias."""
        resultado = []
        ini = date.fromisoformat(data_inicio)
        fim = date.fromisoformat(data_termino)
        cursor = ini
        while cursor <= fim:
            fatia_fim = min(cursor + timedelta(days=9), fim)
            page, page_size = 1, 500
            while True:
                url = (
                    f"{BASE_URL}/v7/Agendamento/Estabelecimento"
                    f"/{self.estabelecimento_id}"
                    f"/{cursor.isoformat()}/{fatia_fim.isoformat()}/{page}/{page_size}"
                )
                items = self._items(self._get(url))
                resultado.extend(items)
                if len(items) < page_size:
                    break
                page += 1
            cursor = fatia_fim + timedelta(days=1)
        return resultado

    # ----------------------------------------------------------------
    # Orçamentos
    # ----------------------------------------------------------------

    def get_orcamentos(self, data_inicio: str, data_termino: str) -> list:
        """Busca mês a mês (API só aceita intervalo no mesmo mês)."""
        resultado = []
        cursor = date.fromisoformat(data_inicio)
        fim = date.fromisoformat(data_termino)
        while cursor <= fim:
            ultimo = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
            fatia_fim = min(ultimo, fim)
            url = (
                f"{BASE_URL}/v4/Orcamentos/Orcamentos"
                f"/{self.estabelecimento_id}/{cursor.isoformat()}/{fatia_fim.isoformat()}"
            )
            resultado.extend(self._items(self._get(url)))
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        return resultado

    # ----------------------------------------------------------------
    # Títulos recebidos
    # ----------------------------------------------------------------

    def get_titulos_recebidos(self, data_inicio: str, data_termino: str) -> list:
        url = (
            f"{BASE_URL}/v4/Titulos/{self.estabelecimento_id}"
            f"/recebidos/{data_inicio}/{data_termino}"
        )
        return self._items(self._get(url))

    # ----------------------------------------------------------------
    # Profissionais
    # ----------------------------------------------------------------

    def get_profissionais(self) -> list:
        url = f"{BASE_URL}/v3/Estabelecimentos/{self.estabelecimento_id}/Profissionais"
        return self._items(self._get(url))

    # ----------------------------------------------------------------
    # Factory: constrói a partir de dados do tenant no DB
    # ----------------------------------------------------------------

    @classmethod
    def from_tenant(cls, tenant: dict) -> "ControleOdontoAPI":
        """Constrói instância a partir do dict retornado por get_tenant()."""
        return cls(
            usuario=tenant.get("co_usuario") or "",
            senha=tenant.get("co_senha") or "",
            estabelecimento_id=tenant.get("co_estab_id") or "",
        )


def get_tenant(tenant_id: str) -> dict | None:
    """Retorna dados do tenant incluindo credenciais CO."""
    from database import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, co_usuario, co_senha, co_estab_id FROM tenants WHERE id=%s",
                (tenant_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "nome": row[1],
        "co_usuario": row[2], "co_senha": row[3], "co_estab_id": row[4],
    }
