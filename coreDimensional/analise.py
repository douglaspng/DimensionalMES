from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any


def ler_telemetria(caminho: str | Path) -> list[dict[str, str]]:
    caminho = Path(caminho)
    if not caminho.exists():
        return []
    with caminho.open(newline="", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def estatisticas_descritivas(linhas: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    valores_por_variavel: dict[str, list[float]] = defaultdict(list)
    for linha in linhas:
        try:
            valores_por_variavel[linha["variable"]].append(float(linha["value"]))
        except (KeyError, TypeError, ValueError):
            continue

    resultado: dict[str, dict[str, Any]] = {}
    for variavel, valores in valores_por_variavel.items():
        resultado[variavel] = {
            "quantidade": len(valores), "media": round(mean(valores), 4),
            "mediana": round(median(valores), 4), "minimo": min(valores),
            "maximo": max(valores),
            "desvio_padrao": round(pstdev(valores), 4) if len(valores) > 1 else 0.0
        }
    return resultado


def detectar_anomalias(linhas: list[dict[str, str]], contaminação: float = 0.05) -> list[dict[str, Any]]:
    """Aplica Isolation Forest; usa z-score se a biblioteca não estiver instalada."""
    linhas_numericas: list[tuple[int, float]] = []
    for indice, linha in enumerate(linhas):
        try:
            linhas_numericas.append((indice, float(linha["value"])))
        except (KeyError, TypeError, ValueError):
            continue

    if len(linhas_numericas) < 5:
        return _detectar_por_zscore(linhas)

    try:
        from sklearn.ensemble import IsolationForest
        modelo = IsolationForest(contamination=contaminação, random_state=42)
        entradas = [[valor] for _, valor in linhas_numericas]
        previsoes = modelo.fit_predict(entradas)
        pontuacoes = modelo.decision_function(entradas)
        resultado = [dict(linha, is_anomaly=False, anomaly_score=None) for linha in linhas]
        for (indice, _), previsao, pontuacao in zip(linhas_numericas, previsoes, pontuacoes):
            resultado[indice]["is_anomaly"] = bool(previsao == -1)
            resultado[indice]["anomaly_score"] = round(float(pontuacao), 6)
        return resultado
    except ImportError:
        return _detectar_por_zscore(linhas)


def _detectar_por_zscore(linhas: list[dict[str, str]], limite: float = 3.0) -> list[dict[str, Any]]:
    valores: dict[str, list[float]] = defaultdict(list)
    for linha in linhas:
        try:
            valores[linha["variable"]].append(float(linha["value"]))
        except (KeyError, TypeError, ValueError):
            pass
    estatisticas = {nome: (mean(lista), pstdev(lista)) for nome, lista in valores.items()}
    resultado = []
    for linha in linhas:
        enriquecida = dict(linha)
        try:
            media, desvio = estatisticas[linha["variable"]]
            zscore = abs(float(linha["value"]) - media) / desvio if desvio else 0.0
            enriquecida["is_anomaly"] = zscore >= limite
            enriquecida["anomaly_score"] = round(zscore, 4)
        except (KeyError, TypeError, ValueError):
            enriquecida["is_anomaly"] = False
            enriquecida["anomaly_score"] = None
        resultado.append(enriquecida)
    return resultado


def gerar_indicadores(linhas: list[dict[str, str]], identificacao_maquina: str) -> dict[str, Any]:
    linhas_com_anomalia = detectar_anomalias(linhas)
    quantidade_anomalias = sum(1 for linha in linhas_com_anomalia if linha.get("is_anomaly"))
    return {
        "machine_id": identificacao_maquina,
        "total_readings": len(linhas),
        "anomalies": {
            "total": quantidade_anomalias,
            "percentage": round(quantidade_anomalias / len(linhas) * 100, 2) if linhas else 0.0
        },
        "variables": estatisticas_descritivas(linhas)
    }
