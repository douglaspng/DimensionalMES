from __future__ import annotations

import random
import sys
from datetime import datetime, timezone
from pathlib import Path


# Localiza a pasta principal do projeto
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ_PROJETO))

from coreDimensional import ConfiguracaoAplicacao, DimensionalMES


def obter_data_hora_atual() -> str:
    """Retorna a data e hora atual em UTC."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def criar_mensagens_simuladas() -> list[dict]:
    """Cria mensagens fictícias no formato enviado pelo Node-RED."""
    mensagens = []

    for contador in range(20):
        mensagens.extend(
            [
                {
                    "timestamp": obter_data_hora_atual(),
                    "node_id": "ns=3;s=Machine.Temperature",
                    "variable": "temperature",
                    "value": round(random.gauss(75, 3), 2),
                    "status_code": 0
                },
                {
                    "timestamp": obter_data_hora_atual(),
                    "node_id": "ns=3;s=Machine.Pressure",
                    "variable": "pressure",
                    "value": round(random.gauss(90, 5), 2),
                    "status_code": 0
                },
                {
                    "timestamp": obter_data_hora_atual(),
                    "node_id": "ns=3;s=Production.CycleTime",
                    "variable": "cycle_time",
                    "value": round(random.gauss(12, 1), 2),
                    "status_code": 0
                },
                {
                    "timestamp": obter_data_hora_atual(),
                    "node_id": "ns=3;s=Production.PieceCounter",
                    "variable": "piece_counter",
                    "value": contador + 1,
                    "status_code": 0
                }
            ]
        )

    return mensagens


def main() -> None:
    """Executa a simulação do Dimensional MES."""
    caminho_configuracao = RAIZ_PROJETO / "config" / "config.json"

    configuracao = ConfiguracaoAplicacao.carregar(caminho_configuracao)
    sistema = DimensionalMES(configuracao)

    mensagens = criar_mensagens_simuladas()
    resultados = sistema.ingerir_lote(mensagens)
    indicadores = sistema.recalcular_indicadores()

    leituras_aceitas = sum(
        1 for resultado in resultados if resultado["aceita"]
    )

    leituras_rejeitadas = len(resultados) - leituras_aceitas

    print("Simulação concluída com sucesso.")
    print(f"Total de leituras: {len(resultados)}")
    print(f"Leituras aceitas: {leituras_aceitas}")
    print(f"Leituras rejeitadas: {leituras_rejeitadas}")
    print(f"Total de anomalias: {indicadores['anomalies']['total']}")
    print("Arquivos CSV e JSON atualizados na pasta data.")


if __name__ == "__main__":
    main()
