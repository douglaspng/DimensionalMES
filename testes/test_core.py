from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from coreDimensional import ConfiguracaoAplicacao, DimensionalMES


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
