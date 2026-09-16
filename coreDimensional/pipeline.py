from __future__ import annotations

from typing import Any

from .alertas import adicionar_alertas, avaliar_alertas
from .analise import gerar_indicadores, ler_telemetria
from .armazenamento import Armazenamento
from .configuracao import ConfiguracaoAplicacao
from .validacao import padronizar_mensagem, validar_leitura


class DimensionalMES:
    """Coordena ingestão, validação, armazenamento e análise."""

    def __init__(self, configuracao: ConfiguracaoAplicacao):
        self.configuracao = configuracao
        self.armazenamento = Armazenamento(
            configuracao.diretorio_raiz / configuracao.armazenamento.get("data_dir", "data")
        )
        prefixo = configuracao.armazenamento.get("telemetry_file_prefix", "telemetria")
        self.arquivo_telemetria = f"{prefixo}.csv"

    def ingerir(self, mensagem: dict[str, Any]) -> dict[str, Any]:
        leitura = padronizar_mensagem(mensagem, self.configuracao.variaveis)
        valida, motivo = validar_leitura(leitura, self.configuracao.variaveis)
        if not valida:
            self.armazenamento.adicionar_invalida(leitura, motivo, self.configuracao.armazenamento.get("invalid_file", "leituras_invalidas.csv"))
            return {"aceita": False, "motivo": motivo, "leitura": leitura}

        leitura["is_anomaly"] = False
        leitura["alert_level"] = "normal"
        alertas = avaliar_alertas(leitura, self.configuracao.variaveis)
        if alertas:
            leitura["alert_level"] = alertas[0]["level"]

        self.armazenamento.adicionar_telemetria(leitura, self.arquivo_telemetria)
        self.armazenamento.atualizar_estado_atual(leitura, {"opcua": "connected", "node_red": "connected"})
        nome_alertas = self.configuracao.armazenamento.get("alerts_file", "alertas.json")
        alertas_atuais = self.armazenamento.ler_json(nome_alertas, [])
        self.armazenamento.salvar_json_seguro(nome_alertas, adicionar_alertas(alertas_atuais, alertas))
        return {"aceita": True, "leitura": leitura, "alertas": alertas}

    def recalcular_indicadores(self) -> dict[str, Any]:
        linhas = ler_telemetria(self.armazenamento.diretorio_dados / self.arquivo_telemetria)
        indicadores = gerar_indicadores(linhas, self.configuracao.identificacao_maquina)
        nome_indicadores = self.configuracao.armazenamento.get("metrics_file", "indicadores.json")
        self.armazenamento.salvar_json_seguro(nome_indicadores, indicadores)
        return indicadores

    def ingerir_lote(self, mensagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resultados = [self.ingerir(mensagem) for mensagem in mensagens]
        self.recalcular_indicadores()
        return resultados
