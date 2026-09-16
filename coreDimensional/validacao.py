from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def padronizar_mensagem(mensagem: dict[str, Any], configuracao: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Converte uma mensagem do Node-RED em uma leitura do Dimensional MES."""
    variavel = str(mensagem.get("variable") or mensagem.get("name") or "desconhecida")
    node_id = str(mensagem.get("node_id") or mensagem.get("nodeId") or mensagem.get("topic") or "")
    if variavel == "desconhecida" and node_id:
        variavel = next((nome for nome, item in configuracao.items() if item.get("node_id") == node_id), variavel)

    return {
        "timestamp": str(mensagem.get("timestamp") or agora_utc()),
        "source_timestamp": mensagem.get("source_timestamp") or mensagem.get("sourceTimestamp"),
        "machine_id": str(mensagem.get("machine_id") or "Smart40-N2"),
        "node_id": node_id,
        "variable": variavel,
        "value": mensagem.get("value", mensagem.get("payload")),
        "unit": configuracao.get(variavel, {}).get("unit", ""),
        "status_code": _converter_status(mensagem.get("status_code", mensagem.get("statusCode", 0)))
    }


def _converter_status(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return -1


def validar_leitura(leitura: dict[str, Any], configuracao: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    if not leitura["node_id"]:
        return False, "NodeId ausente"
    if leitura["status_code"] != 0:
        return False, f"Status OPC UA inválido: {leitura['status_code']}"
    if leitura["value"] is None:
        return False, "Valor ausente"

    definicao = configuracao.get(leitura["variable"], {})
    try:
        valor_numerico = float(leitura["value"])
        if "min" in definicao and valor_numerico < definicao["min"]:
            return False, "Valor abaixo do limite físico"
        if "max" in definicao and valor_numerico > definicao["max"]:
            return False, "Valor acima do limite físico"
    except (TypeError, ValueError):
        pass

    return True, "ok"
