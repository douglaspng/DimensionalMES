from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAMINHO_SCRIPT = Path(__file__).resolve()
RAIZ_PROJETO = None
CAMINHO_CONFIGURACAO = None
for pai in CAMINHO_SCRIPT.parents:
    if not (pai / "coreDimensional").exists():
        continue
    for candidato in (pai / "config.json", pai / "config" / "config.json"):
        if candidato.exists():
            RAIZ_PROJETO = pai
            CAMINHO_CONFIGURACAO = candidato
            break
    if CAMINHO_CONFIGURACAO:
        break

if RAIZ_PROJETO is None or CAMINHO_CONFIGURACAO is None:
    raise FileNotFoundError(
        "Não foi encontrado config.json na raiz do projeto nem em config/config.json. "
        f"Diretório do script: {CAMINHO_SCRIPT.parent}"
    )
sys.path.insert(0, str(RAIZ_PROJETO))

from coreDimensional import ConfiguracaoAplicacao, DimensionalMES


NODE_IDS = {
    "temperature": "ns=3;s=Machine.Temperature",
    "pressure": "ns=3;s=Machine.Pressure",
    "cycle_time": "ns=3;s=Production.CycleTime",
    "piece_counter": "ns=3;s=Production.PieceCounter",
    "machine_status": "ns=3;s=Machine.Status",
}


def instante_iso(instante: datetime) -> str:
    return instante.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def turno_do_horario(instante: datetime) -> str:
    hora = instante.hour
    if 6 <= hora < 14:
        return "Turno A"
    if 14 <= hora < 22:
        return "Turno B"
    return "Turno C"


def gerar_leituras(
    dias: int = 3,
    intervalo_minutos: int = 5,
    incluir_eventos: bool = True,
    semente: int = 40,
) -> list[dict]:
    """Gera telemetria temporal para a célula N2.

    A simulação inclui variação por horário, turnos, aquecimento do processo,
    contador acumulado, estados de máquina e alguns eventos críticos controlados.
    """
    aleatorio = random.Random(semente)
    inicio = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=dias - 1)
    total_instantes = max(1, int((dias * 24 * 60) / intervalo_minutos))
    contador = 1000
    mensagens: list[dict] = []

    for indice in range(total_instantes):
        instante = inicio + timedelta(minutes=indice * intervalo_minutos)
        hora_decimal = instante.hour + instante.minute / 60
        ciclo_diario = math.sin((hora_decimal - 6) * math.pi / 12)
        turno = turno_do_horario(instante)
        em_parada_programada = instante.hour == 12 and instante.minute < intervalo_minutos
        evento_temperatura = incluir_eventos and indice == int(total_instantes * 0.42)
        evento_pressao = incluir_eventos and indice == int(total_instantes * 0.68)
        em_evento = evento_temperatura or evento_pressao

        carga = max(0.0, ciclo_diario) * 3.5
        temperatura = 74 + carga + aleatorio.gauss(0, 1.8)
        pressao = 88 + carga * 1.8 + aleatorio.gauss(0, 2.8)
        tempo_ciclo = max(7.0, 12.5 - carga * 0.35 + aleatorio.gauss(0, 0.7))
        estado = 0 if em_parada_programada else 1

        if evento_temperatura:
            temperatura = 245.0
        if evento_pressao:
            pressao = 20.0
        if em_parada_programada:
            tempo_ciclo = 0.0

        pecas_no_intervalo = 0 if em_parada_programada else max(
            0, round(5 + carga + aleatorio.gauss(0, 1))
        )
        contador += pecas_no_intervalo
        timestamp = instante_iso(instante)
        contexto = {"timestamp": timestamp, "source_timestamp": timestamp, "turno": turno}

        valores = [
            ("temperature", round(temperatura, 2)),
            ("pressure", round(pressao, 2)),
            ("cycle_time", round(tempo_ciclo, 2)),
            ("piece_counter", contador),
            ("machine_status", estado),
        ]
        for variavel, valor in valores:
            mensagens.append({
                **contexto,
                "node_id": NODE_IDS[variavel],
                "variable": variavel,
                "value": valor,
                "status_code": 0,
            })

    return mensagens


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador temporal da célula Smart 4.0 N2")
    parser.add_argument("--dias", type=int, default=3, help="Quantidade de dias simulados")
    parser.add_argument("--intervalo", type=int, default=5, help="Intervalo entre leituras, em minutos")
    parser.add_argument("--sem-eventos", action="store_true", help="Não gerar eventos críticos")
    parser.add_argument("--semente", type=int, default=40, help="Semente para repetir o mesmo cenário")
    args = parser.parse_args()

    raiz = RAIZ_PROJETO
    sistema = DimensionalMES(ConfiguracaoAplicacao.carregar(CAMINHO_CONFIGURACAO))
    mensagens = gerar_leituras(
        dias=max(1, args.dias),
        intervalo_minutos=max(1, args.intervalo),
        incluir_eventos=not args.sem_eventos,
        semente=args.semente,
    )
    resultados = sistema.ingerir_lote(mensagens)
    indicadores = sistema.recalcular_indicadores()
    aceitas = sum(1 for resultado in resultados if resultado["aceita"])
    criticos = sum(1 for resultado in resultados if resultado.get("alerta_critico"))

    print("Simulação enriquecida da N2 concluída")
    print(f"Período simulado: {args.dias} dia(s), intervalo de {args.intervalo} minuto(s)")
    print(f"Total de mensagens: {len(mensagens)}")
    print(f"Leituras aceitas: {aceitas}")
    print(f"Leituras rejeitadas: {len(mensagens) - aceitas}")
    print(f"Alertas críticos gerados: {criticos}")
    print(f"Total de leituras nos indicadores: {indicadores.get('total_readings', 0)}")
    print(f"Dados gravados em: {sistema.armazenamento.diretorio_dados}")


if __name__ == "__main__":
    main()
