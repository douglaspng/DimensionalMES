from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coreDimensional import ConfiguracaoAplicacao, DimensionalMES
from coreDimensional.notificacoes import (
    avaliar_alerta_critico,
    notificar_email_se_configurado,
)


class TesteNucleoDimensionalMES(unittest.TestCase):
    """Testes principais do núcleo do Dimensional MES."""

    def criar_sistema(self, diretorio_projeto: Path, variaveis: dict) -> DimensionalMES:
        """Cria uma configuração temporária para os testes."""
        caminho_configuracao = diretorio_projeto / "config.json"
        caminho_configuracao.write_text(
            json.dumps(
                {
                    "machine_id": "maquina-teste",
                    "storage": {
                        "data_dir": "data",
                        "telemetry_file_prefix": "telemetria",
                        "current_state_file": "estado_atual.json",
                        "alerts_file": "alertas.json",
                        "metrics_file": "indicadores.json",
                        "invalid_file": "leituras_invalidas.csv"
                    },
                    "variables": variaveis
                },
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        configuracao = ConfiguracaoAplicacao.carregar(caminho_configuracao)
        return DimensionalMES(configuracao)

    def test_deve_aceitar_leitura_valida(self):
        """Verifica se uma leitura válida é aceita e armazenada."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "temperatura": {
                        "node_id": "ns=3;s=Temperatura",
                        "unit": "C",
                        "min": 0,
                        "max": 250,
                        "warning_high": 220
                    }
                }
            )

            resultado = sistema.ingerir(
                {
                    "node_id": "ns=3;s=Temperatura",
                    "variable": "temperatura",
                    "value": 72.4,
                    "status_code": 0
                }
            )

            self.assertTrue(resultado["aceita"])
            self.assertTrue((diretorio_projeto / "data" / "telemetria.csv").exists())
            self.assertTrue((diretorio_projeto / "data" / "estado_atual.json").exists())

    def test_deve_rejeitar_leitura_acima_do_limite_fisico(self):
        """Verifica se valores fisicamente inválidos são rejeitados."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "temperatura": {
                        "node_id": "ns=3;s=Temperatura",
                        "unit": "C",
                        "min": 0,
                        "max": 250
                    }
                }
            )

            resultado = sistema.ingerir(
                {
                    "node_id": "ns=3;s=Temperatura",
                    "variable": "temperatura",
                    "value": 999,
                    "status_code": 0
                }
            )

            self.assertFalse(resultado["aceita"])
            self.assertIn("limite físico", resultado["motivo"])
            self.assertTrue((diretorio_projeto / "data" / "leituras_invalidas.csv").exists())

    def test_deve_rejeitar_status_opcua_invalido(self):
        """Verifica se uma leitura com status OPC UA inválido é rejeitada."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "pressao": {
                        "node_id": "ns=3;s=Pressao",
                        "unit": "bar",
                        "min": 0,
                        "max": 300
                    }
                }
            )

            resultado = sistema.ingerir(
                {
                    "node_id": "ns=3;s=Pressao",
                    "variable": "pressao",
                    "value": 85.2,
                    "status_code": 1
                }
            )

            self.assertFalse(resultado["aceita"])
            self.assertIn("Status OPC UA inválido", resultado["motivo"])

    def test_deve_gerar_alerta_de_limite(self):
        """Verifica se uma leitura próxima do limite gera alerta."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "temperatura": {
                        "node_id": "ns=3;s=Temperatura",
                        "unit": "C",
                        "min": 0,
                        "max": 250,
                        "warning_high": 220
                    }
                }
            )

            resultado = sistema.ingerir(
                {
                    "node_id": "ns=3;s=Temperatura",
                    "variable": "temperatura",
                    "value": 230,
                    "status_code": 0
                }
            )

            self.assertTrue(resultado["aceita"])
            self.assertEqual(resultado["leitura"]["alert_level"], "warning")
            self.assertEqual(len(resultado["alertas"]), 1)

    def test_deve_gerar_indicadores_estatisticos(self):
        """Verifica a geração dos indicadores a partir do histórico."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "pressao": {
                        "node_id": "ns=3;s=Pressao",
                        "unit": "bar",
                        "min": 0,
                        "max": 300
                    }
                }
            )

            sistema.ingerir_lote(
                [
                    {
                        "node_id": "ns=3;s=Pressao",
                        "variable": "pressao",
                        "value": 80,
                        "status_code": 0
                    },
                    {
                        "node_id": "ns=3;s=Pressao",
                        "variable": "pressao",
                        "value": 90,
                        "status_code": 0
                    }
                ]
            )

            indicadores = sistema.recalcular_indicadores()

            self.assertEqual(indicadores["total_readings"], 2)
            self.assertEqual(indicadores["variables"]["pressao"]["media"], 85.0)
            self.assertTrue((diretorio_projeto / "data" / "indicadores.json").exists())

    def test_deve_identificar_alerta_critico_de_temperatura(self):
        """Verifica a detecção de temperatura acima do limite crítico."""
        alerta = avaliar_alerta_critico(
            {"variable": "temperatura", "value": 245, "timestamp": "2026-09-25T00:00:00Z"},
            {"temperatura": {"unit": "C", "critical_high": 240}},
        )

        self.assertIsNotNone(alerta)
        self.assertEqual(alerta["level"], "critical")
        self.assertEqual(alerta["direcao"], "alta")

    def test_pipeline_registra_critico_sem_interromper_sem_smtp(self):
        """Sem SMTP configurado, a leitura continua e o crítico é persistido."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "pressao": {
                        "node_id": "ns=3;s=Pressao",
                        "unit": "bar",
                        "min": 0,
                        "max": 300,
                        "critical_low": 25,
                    }
                },
            )

            with patch.dict(
                "os.environ",
                {
                    "SMTP_SERVIDOR": "",
                    "SMTP_USUARIO": "",
                    "SMTP_SENHA": "",
                    "EMAIL_DESTINATARIO": "",
                },
                clear=False,
            ):
                resultado = sistema.ingerir(
                    {
                        "node_id": "ns=3;s=Pressao",
                        "variable": "pressao",
                        "value": 20,
                        "status_code": 0,
                    }
                )

            self.assertTrue(resultado["aceita"])
            self.assertEqual(resultado["leitura"]["alert_level"], "critical")
            self.assertEqual(resultado["notificacao"]["motivo"], "smtp_nao_configurado")
            alertas = json.loads((diretorio_projeto / "data" / "alertas.json").read_text(encoding="utf-8"))
            self.assertEqual(alertas[-1]["level"], "critical")

    def test_leitura_normal_nao_gera_alerta_critico(self):
        """Valores dentro da faixa não devem gerar notificação crítica."""
        alerta = avaliar_alerta_critico(
            {"variable": "pressao", "value": 80},
            {"pressao": {"unit": "bar", "critical_low": 25}},
        )
        self.assertIsNone(alerta)

    def test_deve_identificar_pressao_abaixo_do_limite_critico(self):
        """Verifica a direção e os dados de uma pressão crítica baixa."""
        alerta = avaliar_alerta_critico(
            {
                "machine_id": "maquina-teste",
                "variable": "pressao",
                "value": 20,
                "timestamp": "2026-09-25T00:00:00Z",
            },
            {"pressao": {"unit": "bar", "critical_low": 25}},
        )
        self.assertIsNotNone(alerta)
        self.assertEqual(alerta["direcao"], "baixa")
        self.assertEqual(alerta["limite"], 25.0)
        self.assertEqual(alerta["machine_id"], "maquina-teste")

    def test_notificacao_sem_smtp_informa_motivo(self):
        """A ausência de SMTP deve ser informada sem lançar exceção."""
        alerta = {
            "variavel": "temperatura",
            "direcao": "alta",
            "valor": 245,
            "limite": 240,
            "unidade": "C",
            "timestamp": "2026-09-25T00:00:00Z",
            "mensagem": "temperatura crítica",
        }
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            with patch.dict(
                "os.environ",
                {
                    "SMTP_SERVIDOR": "",
                    "SMTP_USUARIO": "",
                    "SMTP_SENHA": "",
                    "EMAIL_DESTINATARIO": "",
                },
                clear=False,
            ):
                resultado = notificar_email_se_configurado(
                    alerta,
                    Path(diretorio_temporario) / "notificacoes.json",
                )
        self.assertFalse(resultado["enviada"])
        self.assertEqual(resultado["motivo"], "smtp_nao_configurado")

    def test_notificacao_respeita_cooldown(self):
        """O segundo evento igual dentro da janela não deve reenviar e-mail."""
        alerta = {
            "variavel": "pressao",
            "direcao": "baixa",
            "valor": 20,
            "limite": 25,
            "unidade": "bar",
            "timestamp": "2026-09-25T00:00:00Z",
            "mensagem": "pressão crítica",
        }
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            caminho_controle = Path(diretorio_temporario) / "notificacoes.json"
            with patch.dict(
                "os.environ",
                {
                    "SMTP_SERVIDOR": "smtp.teste.local",
                    "SMTP_USUARIO": "usuario",
                    "SMTP_SENHA": "senha",
                    "EMAIL_DESTINATARIO": "destino@teste.local",
                },
                clear=False,
            ), patch("coreDimensional.notificacoes.enviar_email_alerta") as enviar:
                primeira = notificar_email_se_configurado(alerta, caminho_controle)
                segunda = notificar_email_se_configurado(alerta, caminho_controle)

        self.assertTrue(primeira["enviada"])
        self.assertEqual(segunda["motivo"], "cooldown")
        self.assertEqual(enviar.call_count, 1)

    def test_lote_misto_preserva_leituras_validas_e_invalidas(self):
        """Um lote deve aceitar boas leituras sem perder o registro de falhas."""
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            diretorio_projeto = Path(diretorio_temporario)
            sistema = self.criar_sistema(
                diretorio_projeto,
                {
                    "temperatura": {
                        "node_id": "ns=3;s=Temperatura",
                        "unit": "C",
                        "min": 0,
                        "max": 250,
                    }
                },
            )
            resultados = sistema.ingerir_lote(
                [
                    {"node_id": "ns=3;s=Temperatura", "variable": "temperatura", "value": 70, "status_code": 0},
                    {"node_id": "ns=3;s=Temperatura", "variable": "temperatura", "value": 999, "status_code": 0},
                ]
            )
            self.assertEqual([resultado["aceita"] for resultado in resultados], [True, False])
            linhas = (diretorio_projeto / "data" / "telemetria.csv").read_text(encoding="utf-8").splitlines()
            invalidas = (diretorio_projeto / "data" / "leituras_invalidas.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(linhas), 2)
            self.assertEqual(len(invalidas), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
