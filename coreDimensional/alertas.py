from __future__ import annotations

from typing import Any


def avaliar_alertas(leitura: dict[str, Any], configuracao: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    definicao = configuracao.get(leitura["variable"], {})
    alertas: list[dict[str, Any]] = []
    try:
        valor = float(leitura["value"])
    except (TypeError, ValueError):
        return alertas

    if "warning_high" in definicao and valor >= definicao["warning_high"]:
        alertas.append({
            "timestamp": leitura["timestamp"], "machine_id": leitura["machine_id"],
            "variable": leitura["variable"], "value": valor, "level": "warning",
            "message": f"{leitura['variable']} acima do limite de atenção"
        })
    if "warning_low" in definicao and valor <= definicao["warning_low"]:
        alertas.append({
            "timestamp": leitura["timestamp"], "machine_id": leitura["machine_id"],
            "variable": leitura["variable"], "value": valor, "level": "warning",
            "message": f"{leitura['variable']} abaixo do limite de atenção"
        })
    return alertas


def adicionar_alertas(alertas_atuais: list[dict[str, Any]], novos_alertas: list[dict[str, Any]], limite: int = 500) -> list[dict[str, Any]]:
    return (alertas_atuais + novos_alertas)[-limite:]
