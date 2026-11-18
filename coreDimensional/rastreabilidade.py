from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


CAMPOS_RASTREABILIDADE = [
    "reading_id",
    "production_order_id",
    "batch_id",
    "product_id",
    "shift",
    "sequence_number",
]


def agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _primeiro_valor(mensagem: dict[str, Any], *nomes: str) -> Any:
    for nome in nomes:
        valor = mensagem.get(nome)
        if valor not in (None, ""):
            return valor
    return None


def criar_contexto_rastreabilidade(
    mensagem: dict[str, Any],
    configuracao: dict[str, Any] | None = None,
    sequencia: int | None = None,
) -> dict[str, Any]:
    """Normaliza o vínculo da leitura com ordem, lote, produto e turno.

    Os campos são opcionais para preservar compatibilidade com mensagens antigas.
    Quando a configuração permite, identificadores padrão são gerados para facilitar
    a operação do simulador e a demonstração do protótipo.
    """
    configuracao = configuracao or {}
    rastreabilidade = configuracao.get("rastreabilidade", {})
    gerar_padrao = bool(rastreabilidade.get("gerar_identificadores", True))

    ordem = _primeiro_valor(
        mensagem, "production_order_id", "production_order", "ordem_producao", "ordem"
    )
    lote = _primeiro_valor(mensagem, "batch_id", "batch", "lote")
    produto = _primeiro_valor(mensagem, "product_id", "product", "produto")
    turno = _primeiro_valor(mensagem, "shift", "turno")
    sequencia_mensagem = _primeiro_valor(mensagem, "sequence_number", "sequencia")

    if gerar_padrao:
        ordem = ordem or rastreabilidade.get("ordem_padrao")
        lote = lote or rastreabilidade.get("lote_padrao")
        produto = produto or rastreabilidade.get("produto_padrao")
        turno = turno or rastreabilidade.get("turno_padrao")

    try:
        sequencia_final = int(sequencia_mensagem if sequencia_mensagem is not None else sequencia or 0)
    except (TypeError, ValueError):
        sequencia_final = int(sequencia or 0)

    leitura_id = _primeiro_valor(mensagem, "reading_id", "id_leitura")
    leitura_id = str(leitura_id or f"LEIT-{uuid4().hex[:12].upper()}")

    return {
        "reading_id": leitura_id,
        "production_order_id": str(ordem) if ordem not in (None, "") else "",
        "batch_id": str(lote) if lote not in (None, "") else "",
        "product_id": str(produto) if produto not in (None, "") else "",
        "shift": str(turno) if turno not in (None, "") else "",
        "sequence_number": sequencia_final,
    }


def validar_contexto_rastreabilidade(contexto: dict[str, Any]) -> tuple[bool, str]:
    """Valida apenas coerência básica, sem bloquear telemetria legada."""
    if not contexto.get("reading_id"):
        return False, "Identificador da leitura ausente"
    try:
        if int(contexto.get("sequence_number", 0)) < 0:
            return False, "Sequência de leitura inválida"
    except (TypeError, ValueError):
        return False, "Sequência de leitura inválida"
    return True, "ok"


def resumo_rastreabilidade(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    """Gera um resumo simples por ordem, lote e produto para o dashboard."""
    grupos: dict[tuple[str, str, str], int] = {}
    for linha in linhas:
        chave = (
            str(linha.get("production_order_id", "") or "Não informado"),
            str(linha.get("batch_id", "") or "Não informado"),
            str(linha.get("product_id", "") or "Não informado"),
        )
        grupos[chave] = grupos.get(chave, 0) + 1
    return {
        "total_leituras": len(linhas),
        "total_vinculadas": sum(valor for chave, valor in grupos.items() if chave[0] != "Não informado" or chave[1] != "Não informado"),
        "grupos": [
            {
                "production_order_id": chave[0],
                "batch_id": chave[1],
                "product_id": chave[2],
                "readings": quantidade,
            }
            for chave, quantidade in sorted(grupos.items())
        ],
    }
