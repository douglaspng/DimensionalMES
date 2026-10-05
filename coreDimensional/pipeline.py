from __future__ import annotations

from typing import Any

from .alertas import adicionar_alertas, avaliar_alertas
from .analise import gerar_indicadores, ler_telemetria
from .armazenamento import Armazenamento
from .configuracao import ConfiguracaoAplicacao
from .notificacoes import avaliar_alerta_critico, notificar_email_se_configurado
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
        self.arquivo_controle_notificacoes = configuracao.armazenamento.get(
            "notification_control_file", "notificacoes_enviadas.json"
        )

    def ingerir(self, mensagem: dict[str, Any]) -> dict[str, Any]:
        leitura = padronizar_mensagem(mensagem, self.configuracao.variaveis)
        valida, motivo = validar_leitura(leitura, self.configuracao.variaveis)
        if not valida:
            self.armazenamento.adicionar_invalida(leitura, motivo, self.configuracao.armazenamento.get("invalid_file", "leituras_invalidas.csv"))
            return {"aceita": False, "motivo": motivo, "leitura": leitura}

        leitura["is_anomaly"] = False
        leitura["alert_level"] = "normal"
        alertas = avaliar_alertas(leitura, self.configuracao.variaveis)
        alerta_critico = avaliar_alerta_critico(leitura, self.configuracao.variaveis)
        resultado_notificacao = None
        if alerta_critico:
            resultado_notificacao = notificar_email_se_configurado(
                alerta_critico,
                self.armazenamento.diretorio_dados / self.arquivo_controle_notificacoes,
            )
            alerta_critico["notificacao_email"] = resultado_notificacao
            alertas.append(alerta_critico)
            leitura["alert_level"] = "critical"
        if alertas:
            leitura["alert_level"] = "critical" if alerta_critico else alertas[0]["level"]

        self.armazenamento.adicionar_telemetria(leitura, self.arquivo_telemetria)
        self.armazenamento.atualizar_estado_atual(leitura, {"opcua": "connected", "node_red": "connected"})
        nome_alertas = self.configuracao.armazenamento.get("alerts_file", "alertas.json")
        alertas_atuais = self.armazenamento.ler_json(nome_alertas, [])
        self.armazenamento.salvar_json_seguro(nome_alertas, adicionar_alertas(alertas_atuais, alertas))
        return {
            "aceita": True,
            "leitura": leitura,
            "alertas": alertas,
            "alerta_critico": alerta_critico,
            "notificacao": resultado_notificacao,
        }

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
