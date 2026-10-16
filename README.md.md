# Dimensional MES

O **Dimensional MES** é um protótipo de sistema de execução e monitoramento de manufatura para uma célula **Smart 4.0**. Ele coleta dados industriais, valida leituras, armazena históricos, identifica anomalias, gera alertas e apresenta indicadores em um dashboard interativo.

## Arquitetura

```text
CLP / Sensores → OPC UA → Node-RED → MQTT/HTTP → Python → CSV/JSON → Streamlit
```

## Tecnologias

- **Python**: processamento, validação, alertas e análises;
- **Node-RED e OPC UA**: integração com equipamentos industriais;
- **CSV e JSON**: armazenamento dos dados;
- **Pandas e Scikit-learn**: análise e detecção de anomalias;
- **Streamlit e Plotly**: dashboard e gráficos interativos;
- **Unittest**: testes automatizados.

## Funcionalidades

- Monitoramento de temperatura, pressão, tempo de ciclo e produção;
- Armazenamento de telemetria em CSV;
- Indicadores e estado atual em JSON;
- Alertas de atenção e criticidade;
- Detecção de anomalias;
- Produção diária e horária;
- Dashboard com filtros, cores configuráveis e atualização automática;
- Simulação de dados da célula N2.

## Execução rápida no PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python .\exec\scripts\simulate.py --dias 3 --intervalo 5
python -m streamlit run .\exec\app.py
```

O dashboard estará disponível em:

```text
http://localhost:8501
```

## Observação

O projeto pode operar em modo de simulação. A integração real depende do endpoint OPC UA, dos NodeIds, das credenciais e dos limites operacionais da máquina.
