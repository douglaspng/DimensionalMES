from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    px = None
    go = None


# -----------------------------------------------------------------------------
# Configuração da página
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Dimensional MES | Cockpit Industrial",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp { background: #e2e8ef; color: #26384c; }
        [data-testid="stSidebar"] { background: #1c2d45; }
        [data-testid="stSidebar"] * { color: #f5f8ff !important; }
        [data-testid="stHeader"] { background: #091321; }
        .block-container { padding-top: 1.5rem; }
        .cabecalho {
            background: linear-gradient(120deg, #203752 0%, #2b6579 100%);
            padding: 1.6rem 2rem; border-radius: 18px; color: white;
            margin-bottom: 1.2rem; box-shadow: 0 8px 24px rgba(16,35,63,.18);
        }
        .cabecalho h1 { margin: 0; font-size: 2.15rem; }
        .cabecalho p { margin: .35rem 0 0; opacity: .86; }
        .cartao {
            background: #d2dce7; border-radius: 14px; padding: 1rem 1.15rem;
            border: 1px solid #c0ccd9; box-shadow: 0 4px 14px rgba(35,55,75,.10);
        }
        .status-ok { color: #138a55; font-weight: 700; }
        .status-atencao { color: #c77b00; font-weight: 700; }
        .status-erro { color: #c0392b; font-weight: 700; }
        div[data-testid="stMetric"] { background: #d2dce7; border-radius: 14px; padding: .8rem; border: 1px solid #c0ccd9; box-shadow: 0 4px 14px rgba(35,55,75,.10); }
        div[data-testid="stMetricLabel"] { color: #53677c !important; }
        div[data-testid="stMetricValue"] { color: #203247 !important; }
        div[data-testid="stMetricDelta"] { color: #53677c !important; }
        h1, h2, h3, h4 { color: #26384c !important; }
        p, label, [data-testid="stCaptionContainer"] { color: #53677c; }
        [data-testid="stDataFrame"] { border: 1px solid #c0ccd9; }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Localização dos arquivos
# -----------------------------------------------------------------------------
RAIZ_PROJETO = Path(__file__).resolve().parents[1]
CAMINHOS_DADOS = [
    RAIZ_PROJETO / "data",
    RAIZ_PROJETO / "exec" / "data",
]
DIRETORIO_DADOS = next(
    (caminho for caminho in CAMINHOS_DADOS if (caminho / "telemetria.csv").exists()),
    CAMINHOS_DADOS[0],
)
ARQUIVO_TELEMETRIA = DIRETORIO_DADOS / "telemetria.csv"
ARQUIVO_ESTADO = DIRETORIO_DADOS / "estado_atual.json"
ARQUIVO_ALERTAS = DIRETORIO_DADOS / "alertas.json"
ARQUIVO_INDICADORES = DIRETORIO_DADOS / "indicadores.json"


def ler_json(caminho: Path, padrao):
    if not caminho.exists():
        return padrao
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return padrao


def nome_amigavel(nome: str) -> str:
    nomes = {
        "temperature": "Temperatura",
        "pressure": "Pressão",
        "cycle_time": "Tempo de ciclo",
        "piece_counter": "Contador de peças",
        "machine_status": "Estado da máquina",
    }
    return nomes.get(str(nome), str(nome).replace("_", " ").title())


def numero(valor, casas: int = 2) -> str:
    if pd.isna(valor):
        return "—"
    return f"{float(valor):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def preparar_producao(dados: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula produção diária e horária a partir do contador de peças.

    Quando existe um contador acumulado, a produção é calculada pela diferença
    entre o maior e o menor contador de cada período. Caso não exista contador,
    cada leitura é tratada como uma peça registrada.
    """
    base = dados.dropna(subset=["timestamp"]).copy()
    base["dia"] = base["timestamp"].dt.date
    base["hora"] = base["timestamp"].dt.floor("h")
    contador = base[base["variable"] == "piece_counter"].copy()

    if not contador.empty:
        diaria = contador.groupby("dia")["value"].agg(
            contador_inicial="min", contador_final="max", leituras="count"
        ).reset_index()
        horaria = contador.groupby("hora")["value"].agg(
            contador_inicial="min", contador_final="max", leituras="count"
        ).reset_index()
        diaria["producao"] = (diaria["contador_final"] - diaria["contador_inicial"]).clip(lower=0)
        horaria["producao"] = (horaria["contador_final"] - horaria["contador_inicial"]).clip(lower=0)
    else:
        diaria = base.groupby("dia").size().reset_index(name="producao")
        horaria = base.groupby("hora").size().reset_index(name="producao")
        diaria["leituras"] = diaria["producao"]
        horaria["leituras"] = horaria["producao"]

    return diaria, horaria


def calcular_desempenho(
    dados: pd.DataFrame, diaria: pd.DataFrame, indicadores_atuais: dict
) -> dict[str, float | str]:
    """Calcula indicadores disponíveis no CSV atual, sem inventar OEE."""
    ciclos = dados.loc[dados["variable"] == "cycle_time", "value"].dropna()
    producao_total = float(diaria["producao"].sum()) if not diaria.empty else 0.0
    media_ciclo = float(ciclos.mean()) if not ciclos.empty else 0.0
    leituras_validas = float((dados.get("status_code", 0) == 0).mean() * 100)
    return {
        "producao_total": producao_total,
        "media_ciclo": media_ciclo,
        "leituras_validas": leituras_validas,
        "taxa_anomalias": float(indicadores_atuais.get("anomalies", {}).get("percentage", 0.0)),
        "observacao": "OEE completo depende de tempo planejado, paradas e peças aprovadas/rejeitadas."
    }


st.markdown(
    """
    <div class="cabecalho">
        <h1>Dimensional MES</h1>
        <p>Cockpit inteligente de monitoramento da célula Smart 4.0 modular</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not ARQUIVO_TELEMETRIA.exists():
    st.warning("Nenhum dado encontrado. Execute o simulador antes de abrir o dashboard.")
    st.write("Caminho procurado:")
    st.code(str(ARQUIVO_TELEMETRIA), language="text")
    st.code("python .\\exec\\scripts\\simulate.py", language="powershell")
    st.stop()

try:
    dados = pd.read_csv(ARQUIVO_TELEMETRIA)
except Exception as erro:
    st.error(f"Não foi possível ler a telemetria: {erro}")
    st.stop()

if dados.empty:
    st.warning("O arquivo de telemetria está vazio.")
    st.stop()

for coluna in ("value", "status_code"):
    if coluna in dados.columns:
        dados[coluna] = pd.to_numeric(dados[coluna], errors="coerce")

dados["timestamp"] = pd.to_datetime(dados.get("timestamp"), errors="coerce", utc=True)
dados = dados.sort_values("timestamp")
dados["variavel_amigavel"] = dados["variable"].map(nome_amigavel)

estado = ler_json(ARQUIVO_ESTADO, {})
alertas = ler_json(ARQUIVO_ALERTAS, [])
indicadores = ler_json(ARQUIVO_INDICADORES, {})

# -----------------------------------------------------------------------------
# Barra lateral
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Controle do painel")
    st.caption("Filtros da visualização")
    variaveis = sorted(dados["variable"].dropna().unique().tolist())
    selecionadas = st.multiselect(
        "Variáveis monitoradas",
        variaveis,
        default=variaveis,
        format_func=nome_amigavel,
    )
    quantidade_maxima = max(10, len(dados))
    limite = st.slider(
        "Quantidade de leituras",
        min_value=10,
        max_value=quantidade_maxima,
        value=min(200, quantidade_maxima),
    )
    st.divider()
    st.markdown("### Informações do sistema")
    st.write(f"**Máquina:** {estado.get('machine_id', 'Smart40-N2')}")
    st.write(f"**Arquivo:** {ARQUIVO_TELEMETRIA.name}")
    st.write(f"**Atualização:** {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}")
    if st.button("Atualizar dados", use_container_width=True):
        st.rerun()

filtrados = dados[dados["variable"].isin(selecionadas)].tail(limite)

# -----------------------------------------------------------------------------
# KPIs
# -----------------------------------------------------------------------------
ultima_leitura = dados.iloc[-1]
quantidade_anomalias = int(indicadores.get("anomalies", {}).get("total", 0))
quantidade_alertas = len(alertas) if isinstance(alertas, list) else 0
status_conexao = estado.get("connection", {}).get("opcua", "simulação")

st.subheader("Visão geral operacional")
colunas = st.columns(5)
colunas[0].metric("Leituras coletadas", f"{len(dados):,}".replace(",", "."))
colunas[1].metric("Variáveis", dados["variable"].nunique())
colunas[2].metric("Anomalias", quantidade_anomalias)
colunas[3].metric("Alertas registrados", quantidade_alertas)
colunas[4].metric("Última leitura", numero(ultima_leitura["value"]))

status_coluna, qualidade_coluna, resumo_coluna = st.columns([1, 1, 2])
with status_coluna:
    st.markdown('<div class="cartao">', unsafe_allow_html=True)
    st.markdown("### Estado da célula")
    if status_conexao in ("connected", "conectado"):
        st.markdown('<p class="status-ok">● Conectada</p>', unsafe_allow_html=True)
    elif status_conexao == "simulação":
        st.markdown('<p class="status-atencao">● Modo simulação</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="status-erro">● Verificar conexão</p>', unsafe_allow_html=True)
    st.write(f"Última variável: **{nome_amigavel(ultima_leitura['variable'])}**")
    st.write(f"Horário: **{ultima_leitura['timestamp']}**")
    st.markdown("</div>", unsafe_allow_html=True)

with qualidade_coluna:
    st.markdown('<div class="cartao">', unsafe_allow_html=True)
    st.markdown("### Qualidade dos dados")
    status_validos = (dados.get("status_code", pd.Series([0])) == 0).mean() * 100
    st.metric("Leituras válidas", f"{status_validos:.1f}%")
    st.progress(min(1.0, max(0.0, status_validos / 100)))
    st.markdown("</div>", unsafe_allow_html=True)

with resumo_coluna:
    st.markdown('<div class="cartao">', unsafe_allow_html=True)
    st.markdown("### Interpretação rápida")
    if quantidade_anomalias == 0 and quantidade_alertas == 0:
        st.success("Operação estável no conjunto de dados atual.")
    elif quantidade_alertas > 0:
        st.warning("Existem alertas que devem ser avaliados pela equipe de operação.")
    else:
        st.info("Foram identificados comportamentos fora do padrão histórico.")
    st.write("Use os filtros laterais para investigar cada variável individualmente.")
    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Abas analíticas
# -----------------------------------------------------------------------------
aba_monitoramento, aba_producao, aba_analise, aba_alertas, aba_dados = st.tabs(
    [
        "📈 Monitoramento",
        "🏭 Produção e Desempenho",
        "📊 Análise Estatística",
        "🔔 Alertas",
        "🗂️ Dados Brutos",
    ]
)

with aba_monitoramento:
    st.caption("Acompanhamento das variáveis selecionadas ao longo do tempo, em tempo quase real.")
    st.subheader("Tendência das variáveis")
    if filtrados.empty:
        st.info("Selecione ao menos uma variável.")
    elif px is not None:
        grafico = px.line(
            filtrados,
            x="timestamp",
            y="value",
            color="variavel_amigavel",
            markers=True,
            template="plotly_white",
            labels={"timestamp": "Horário", "value": "Valor", "variavel_amigavel": "Variável"},
            hover_data={"timestamp": True, "value": ":.3f", "variavel_amigavel": True, "unit": True},
        )
        grafico.update_layout(
            legend_title_text="", hovermode="x unified", height=480,
            paper_bgcolor="#d2dce7", plot_bgcolor="#d2dce7", font_color="#26384c",
            legend=dict(orientation="h", y=1.08, x=0, font=dict(color="black")),
            margin=dict(l=20, r=20, t=70, b=20),
        )
        grafico.update_xaxes(
            rangeslider_visible=True, tickfont=dict(color="black"), title_font=dict(color="black"),
            rangeselector=dict(buttons=[
                dict(count=1, label="1h", step="hour", stepmode="backward"),
                dict(count=6, label="6h", step="hour", stepmode="backward"),
                dict(step="all", label="Tudo"),
            ])
        )
        grafico.update_yaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
        st.plotly_chart(grafico, use_container_width=True, theme=None)
    else:
        tabela_grafico = filtrados.pivot_table(index="timestamp", columns="variable", values="value", aggfunc="last")
        st.line_chart(tabela_grafico)

    st.subheader("Últimas leituras")
    st.dataframe(
        filtrados[["timestamp", "variavel_amigavel", "value", "unit", "status_code", "alert_level"]].tail(30),
        use_container_width=True,
        hide_index=True,
    )

with aba_producao:
    st.caption("Indicadores de produção e desempenho calculados a partir dos dados coletados. "
               "OEE completo só é exibido quando os dados de tempo planejado e paradas existirem.")
    st.subheader("Controle de produção")
    producao_diaria, producao_horaria = preparar_producao(dados)
    desempenho = calcular_desempenho(dados, producao_diaria, indicadores)

    kpi_producao = st.columns(4)
    kpi_producao[0].metric("Produção registrada", numero(desempenho["producao_total"], 0))
    kpi_producao[1].metric("Média do ciclo", f"{numero(desempenho['media_ciclo'])} s")
    kpi_producao[2].metric("Dados válidos", f"{numero(desempenho['leituras_validas'], 1)}%")
    kpi_producao[3].metric("Taxa de anomalias", f"{numero(desempenho['taxa_anomalias'], 1)}%")

    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("### Produção por dia")
        if not producao_diaria.empty and px is not None:
            grafico_diario = px.bar(
                producao_diaria, x="dia", y="producao", text_auto=True,
                template="plotly_white", labels={"dia": "Dia", "producao": "Peças"}
            )
            grafico_diario.update_layout(height=360, paper_bgcolor="#d2dce7", plot_bgcolor="#d2dce7", font_color="#26384c")
            grafico_diario.update_xaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            grafico_diario.update_yaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            st.plotly_chart(grafico_diario, use_container_width=True, theme=None)
        else:
            st.info("Ainda não há dados suficientes para produção diária.")

    with direita:
        st.markdown("### Produção por hora")
        if not producao_horaria.empty and px is not None:
            grafico_horario = px.bar(
                producao_horaria, x="hora", y="producao", text_auto=True,
                template="plotly_white", labels={"hora": "Hora", "producao": "Peças"}
            )
            grafico_horario.update_layout(height=360, paper_bgcolor="#d2dce7", plot_bgcolor="#d2dce7", font_color="#26384c")
            grafico_horario.update_xaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            grafico_horario.update_yaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            st.plotly_chart(grafico_horario, use_container_width=True, theme=None)
        else:
            st.info("Ainda não há dados suficientes para produção horária.")

    st.markdown("### Séries temporais operacionais")
    variaveis_temporais = [
        variavel for variavel in ["temperature", "pressure", "cycle_time"]
        if variavel in dados["variable"].unique()
    ]
    if variaveis_temporais and px is not None:
        serie = dados[dados["variable"].isin(variaveis_temporais)]
        grafico_series = px.line(
            serie, x="timestamp", y="value", color="variavel_amigavel",
            facet_row="variavel_amigavel", template="plotly_white",
            labels={"timestamp": "Horário", "value": "Valor"}
        )
        grafico_series.update_yaxes(matches=None, tickfont=dict(color="black"), title_font=dict(color="black"))
        grafico_series.update_xaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
        grafico_series.update_layout(height=650, showlegend=False, paper_bgcolor="#d2dce7", plot_bgcolor="#d2dce7", font_color="#26384c")
        st.plotly_chart(grafico_series, use_container_width=True, theme=None)
    else:
        st.info("Adicione temperatura, pressão ou tempo de ciclo para visualizar séries temporais.")

    st.caption(str(desempenho["observacao"]))

with aba_analise:
    st.caption("Estatística descritiva e detecção de padrões fora do comum (Isolation Forest), "
               "distintos dos alertas operacionais de limite fixo, que ficam na aba Alertas.")
    st.subheader("Resumo estatístico por variável")
    resumo = dados.groupby("variavel_amigavel")["value"].agg(
        Leituras="count", Média="mean", Mínimo="min", Máximo="max", Desvio="std"
    ).reset_index()
    for coluna in ["Média", "Mínimo", "Máximo", "Desvio"]:
        resumo[coluna] = resumo[coluna].round(3)
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("### Distribuição dos valores")
        if px is not None:
            histograma = px.histogram(
                filtrados, x="value", color="variavel_amigavel", marginal="box",
                template="plotly_white", labels={"value": "Valor", "variavel_amigavel": "Variável"}
            )
            histograma.update_layout(
                height=360, legend_title_text="", paper_bgcolor="#d2dce7", plot_bgcolor="#d2dce7",
                font_color="#26384c", legend=dict(font=dict(color="black")),
            )
            histograma.update_xaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            histograma.update_yaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            st.plotly_chart(histograma, use_container_width=True, theme=None)
    with direita:
        st.markdown("### Leituras por variável")
        contagens = dados["variavel_amigavel"].value_counts().reset_index()
        contagens.columns = ["Variável", "Quantidade"]
        if px is not None:
            barras = px.bar(contagens, x="Variável", y="Quantidade", color="Quantidade", template="plotly_white")
            barras.update_layout(height=360, coloraxis_showscale=False, paper_bgcolor="#d2dce7", plot_bgcolor="#d2dce7", font_color="#26384c")
            barras.update_xaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            barras.update_yaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
            st.plotly_chart(barras, use_container_width=True, theme=None)

    st.divider()
    st.markdown("### 🔍 Anomalias detectadas (desvio estatístico)")
    st.caption("Identificadas pelo modelo Isolation Forest (com fallback por z-score). "
               "Não são violações de limite fixo — são comportamentos fora do padrão histórico.")
    if "is_anomaly" in dados.columns:
        anomalias = dados[dados["is_anomaly"].astype(str).str.lower().isin(["true", "1"])]
        if anomalias.empty:
            st.info("Nenhuma anomalia foi marcada no CSV atual.")
        else:
            st.warning(f"{len(anomalias)} anomalia(s) identificada(s) no histórico atual.")
            st.dataframe(anomalias.tail(50), use_container_width=True, hide_index=True)
    else:
        st.info("A coluna de anomalia ainda não está presente na telemetria.")

with aba_alertas:
    st.caption("Alertas operacionais gerados por violação de limites físicos definidos em configuração. "
               "Anomalias estatísticas ficam na aba Análise Estatística.")
    st.subheader("Central de alertas")
    if isinstance(alertas, list) and alertas:
        tabela_alertas = pd.DataFrame(alertas)
        st.warning(f"{len(tabela_alertas)} alerta(s) registrado(s) no histórico JSON.")
        st.dataframe(tabela_alertas, use_container_width=True, hide_index=True)
    else:
        st.success("Nenhum alerta operacional registrado.")

with aba_dados:
    st.caption("Estado atual, indicadores calculados e telemetria completa, para inspeção e auditoria.")
    st.subheader("Estado atual da máquina")
    esquerda, direita = st.columns(2)
    with esquerda:
        st.json(estado if estado else {"mensagem": "Estado ainda não disponível"})
    with direita:
        st.json(indicadores if indicadores else {"mensagem": "Indicadores ainda não disponíveis"})
    st.subheader("Telemetria completa")
    st.dataframe(dados.tail(200), use_container_width=True, hide_index=True)

st.caption("Dimensional MES • Protótipo acadêmico de monitoramento e análise industrial")
