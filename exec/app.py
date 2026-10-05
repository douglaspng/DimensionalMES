from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

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
ARQUIVO_CONFIGURACAO_DASHBOARD = DIRETORIO_DADOS / "configuracao_dashboard.json"
CAMINHOS_CONFIGURACAO = [
    RAIZ_PROJETO / "config" / "config.json",
    RAIZ_PROJETO / "config.json",
]


def ler_json(caminho: Path, padrao):
    if not caminho.exists():
        return padrao
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return padrao


def salvar_json(caminho: Path, dados: dict) -> None:
    """Salva preferências sem deixar um JSON parcialmente escrito."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


def avaliar_alertas_visuais(dados: pd.DataFrame, configuracao: dict) -> list[dict]:
    """Identifica leituras fora dos limites configurados para exibição imediata."""
    alertas_visuais = []
    variaveis_configuradas = configuracao.get("variables", {})
    for variavel, limites in variaveis_configuradas.items():
        leituras = dados[dados["variable"] == variavel]
        if leituras.empty:
            continue
        for _, leitura in leituras.iterrows():
            valor = leitura.get("value")
            if pd.isna(valor):
                continue
            limite_inferior = limites.get("warning_low", limites.get("min"))
            limite_superior = limites.get("warning_high", limites.get("max"))
            if limite_superior is not None and valor > limite_superior:
                alertas_visuais.append({
                    "variavel": nome_amigavel(variavel), "valor": valor,
                    "limite": limite_superior, "tipo": "alta",
                    "unidade": limites.get("unit", ""), "timestamp": leitura.get("timestamp")
                })
            elif limite_inferior is not None and valor < limite_inferior:
                alertas_visuais.append({
                    "variavel": nome_amigavel(variavel), "valor": valor,
                    "limite": limite_inferior, "tipo": "baixa",
                    "unidade": limites.get("unit", ""), "timestamp": leitura.get("timestamp")
                })
    return alertas_visuais


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


def calcular_desempenho(dados: pd.DataFrame, diaria: pd.DataFrame) -> dict[str, float | str]:
    """Calcula indicadores disponíveis no CSV atual, sem inventar OEE."""
    ciclos = dados.loc[dados["variable"] == "cycle_time", "value"].dropna()
    producao_total = float(diaria["producao"].sum()) if not diaria.empty else 0.0
    media_ciclo = float(ciclos.mean()) if not ciclos.empty else 0.0
    leituras_validas = float((dados.get("status_code", 0) == 0).mean() * 100)
    return {
        "producao_total": producao_total,
        "media_ciclo": media_ciclo,
        "leituras_validas": leituras_validas,
        "taxa_anomalias": float(indicadores.get("anomalies", {}).get("percentage", 0.0)),
        "observacao": "OEE completo depende de tempo planejado, paradas e peças aprovadas/rejeitadas."
    }


def aplicar_estilo_grafico(
    grafico,
    fundo: str,
    exibir_grade: bool,
    altura: int,
    cor_legenda: str,
    cor_rotulos: str,
):
    """Aplica o estilo escolhido pelo usuário a um gráfico Plotly."""
    grafico.update_layout(
        height=altura,
        paper_bgcolor=fundo,
        plot_bgcolor=fundo,
        font_color="#26384c",
        xaxis_showgrid=exibir_grade,
        yaxis_showgrid=exibir_grade,
        legend={"font": {"color": cor_legenda}},
        xaxis={"tickfont": {"color": cor_rotulos}, "title_font": {"color": cor_rotulos}},
        yaxis={"tickfont": {"color": cor_rotulos}, "title_font": {"color": cor_rotulos}},
    )
    return grafico


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
configuracao_salva = ler_json(ARQUIVO_CONFIGURACAO_DASHBOARD, {})
configuracao_projeto = next(
    (ler_json(caminho, {}) for caminho in CAMINHOS_CONFIGURACAO if caminho.exists()),
    {}
)

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
    datas_disponiveis = dados["timestamp"].dropna()
    data_minima = datas_disponiveis.min().date() if not datas_disponiveis.empty else date.today()
    data_maxima = datas_disponiveis.max().date() if not datas_disponiveis.empty else date.today()
    periodo = st.date_input(
        "Período de análise",
        value=(data_minima, data_maxima),
        min_value=data_minima,
        max_value=data_maxima,
    )
    if isinstance(periodo, tuple) and len(periodo) == 2:
        inicio_periodo, fim_periodo = periodo
    else:
        inicio_periodo = fim_periodo = periodo
    quantidade_maxima = max(10, len(dados))
    limite = st.slider(
        "Quantidade de leituras",
        min_value=10,
        max_value=quantidade_maxima,
        value=min(200, quantidade_maxima),
    )
    st.divider()
    with st.expander("Editor visual do dashboard", expanded=True):
        temas_disponiveis = ["plotly_white", "plotly", "ggplot2", "seaborn"]
        tema_grafico = st.selectbox(
            "Tema dos gráficos",
            temas_disponiveis,
            index=temas_disponiveis.index(configuracao_salva.get("tema_grafico", "plotly_white")),
            format_func=lambda tema: {
                "plotly_white": "Claro suave",
                "plotly": "Plotly padrão",
                "ggplot2": "Cinza técnico",
                "seaborn": "Seaborn"
            }.get(tema, tema),
        )
        fundo_grafico = st.color_picker("Fundo dos gráficos", configuracao_salva.get("fundo_grafico", "#d2dce7"))
        cor_texto_legenda = st.color_picker("Cor do texto da legenda", configuracao_salva.get("cor_texto_legenda", "#26384c"))
        cor_rotulos_categoria = st.color_picker(
            "Cor dos rótulos dos eixos/categorias",
            configuracao_salva.get("cor_rotulos_categoria", "#53677c"),
            help="Altera textos como Dia, Hora, Variável e os valores dos eixos.",
        )
        exibir_marcadores = st.checkbox("Exibir marcadores", value=configuracao_salva.get("exibir_marcadores", True))
        exibir_grade = st.checkbox("Exibir linhas de grade", value=configuracao_salva.get("exibir_grade", True))
        exibir_legenda = st.checkbox("Exibir legenda", value=configuracao_salva.get("exibir_legenda", True))
        exibir_tabela = st.checkbox("Exibir tabelas", value=configuracao_salva.get("exibir_tabela", True))
        altura_grafico = st.slider("Altura dos gráficos", 300, 800, int(configuracao_salva.get("altura_grafico", 480)), step=20)
        st.caption("As cores abaixo alteram as linhas e os símbolos da legenda.")
        paleta_padrao = ["#2f80ed", "#eb5757", "#27ae60", "#f2994a", "#9b51e0", "#00a6a6"]
        cores_variaveis = {
            variavel: st.color_picker(
                nome_amigavel(variavel),
                configuracao_salva.get("cores_variaveis", {}).get(
                    variavel, paleta_padrao[indice % len(paleta_padrao)]
                ),
                key=f"cor_{variavel}",
            )
            for indice, variavel in enumerate(variaveis)
        }
        if st.button("Salvar preferências visuais", use_container_width=True):
            salvar_json(ARQUIVO_CONFIGURACAO_DASHBOARD, {
                "tema_grafico": tema_grafico,
                "fundo_grafico": fundo_grafico,
                "cor_texto_legenda": cor_texto_legenda,
                "cor_rotulos_categoria": cor_rotulos_categoria,
                "exibir_marcadores": exibir_marcadores,
                "exibir_grade": exibir_grade,
                "exibir_legenda": exibir_legenda,
                "exibir_tabela": exibir_tabela,
                "altura_grafico": altura_grafico,
                "cores_variaveis": cores_variaveis,
            })
            st.success("Preferências visuais salvas.")
    st.divider()
    st.markdown("### Informações do sistema")
    st.write(f"**Máquina:** {estado.get('machine_id', 'Smart40-N2')}")
    st.write(f"**Arquivo:** {ARQUIVO_TELEMETRIA.name}")
    st.write(f"**Atualização:** {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}")
    if st.button("Atualizar dados", use_container_width=True):
        st.rerun()

    atualizacao_automatica = st.checkbox(
        "Atualização automática a cada 5 segundos",
        value=False,
        help="Recarrega o CSV e os JSONs periodicamente para refletir novas leituras.",
    )

if atualizacao_automatica:
    if st_autorefresh is None:
        st.warning(
            "Instale streamlit-autorefresh para ativar a atualização automática."
        )
    else:
        st_autorefresh(interval=5000, key="atualizacao_dimensional_mes")

dados_periodo = dados[
    (dados["timestamp"].dt.date >= inicio_periodo)
    & (dados["timestamp"].dt.date <= fim_periodo)
]
filtrados = dados_periodo[dados_periodo["variable"].isin(selecionadas)].tail(limite)
alertas_visuais = avaliar_alertas_visuais(dados_periodo, configuracao_projeto)

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

st.subheader("Alertas automáticos de processo")
if alertas_visuais:
    st.error(
        f"{len(alertas_visuais)} leitura(s) ultrapassaram os limites configurados. "
        "Verifique a condição da célula."
    )
    quadro_alertas = pd.DataFrame(alertas_visuais).sort_values("timestamp", ascending=False)
    st.dataframe(
        quadro_alertas.head(20),
        use_container_width=True,
        hide_index=True,
        column_config={
            "variavel": "Variável",
            "valor": st.column_config.NumberColumn("Valor", format="%.2f"),
            "limite": st.column_config.NumberColumn("Limite", format="%.2f"),
            "tipo": "Condição",
            "unidade": "Unidade",
            "timestamp": "Horário",
        },
    )
else:
    st.success("Nenhum limite de temperatura ou pressão foi ultrapassado no período selecionado.")

# -----------------------------------------------------------------------------
# Abas analíticas
# -----------------------------------------------------------------------------
aba_monitoramento, aba_producao, aba_analise, aba_alertas, aba_dados = st.tabs(
    ["Monitoramento", "Produção e desempenho", "Análise estatística", "Alertas", "Dados brutos"]
)

with aba_monitoramento:
    st.subheader("Tendência das variáveis")
    if filtrados.empty:
        st.info("Selecione ao menos uma variável.")
    elif px is not None:
        grafico = px.line(
            filtrados,
            x="timestamp",
            y="value",
            color="variavel_amigavel",
            markers=exibir_marcadores,
            template=tema_grafico,
            labels={"timestamp": "Horário", "value": "Valor", "variavel_amigavel": "Variável"},
            hover_data={"timestamp": True, "value": ":.3f", "variavel_amigavel": True, "unit": True},
        )
        grafico.update_layout(
            legend_title_text="", hovermode="x unified", height=altura_grafico,
            paper_bgcolor=fundo_grafico, plot_bgcolor=fundo_grafico, font_color="#26384c",
            showlegend=exibir_legenda,
            legend=dict(orientation="h", y=1.08, x=0, font={"color": cor_texto_legenda}),
            margin=dict(l=20, r=20, t=70, b=20),
        )
        grafico.for_each_trace(
            lambda trace: trace.update(
                line={"color": cores_variaveis.get(trace.name, "#2f80ed")},
                marker={"color": cores_variaveis.get(trace.name, "#2f80ed")},
            )
        )
        aplicar_estilo_grafico(grafico, fundo_grafico, exibir_grade, altura_grafico, cor_texto_legenda, cor_rotulos_categoria)
        grafico.update_xaxes(rangeslider_visible=True, rangeselector=dict(buttons=[
            dict(count=1, label="1h", step="hour", stepmode="backward"),
            dict(count=6, label="6h", step="hour", stepmode="backward"),
            dict(step="all", label="Tudo"),
        ]))
        st.plotly_chart(grafico, use_container_width=True)
    else:
        tabela_grafico = filtrados.pivot_table(index="timestamp", columns="variable", values="value", aggfunc="last")
        st.line_chart(tabela_grafico)

    if exibir_tabela:
        st.subheader("Últimas leituras")
        st.dataframe(
            filtrados[["timestamp", "variavel_amigavel", "value", "unit", "status_code", "alert_level"]].tail(30),
            use_container_width=True,
            hide_index=True,
        )

with aba_producao:
    st.subheader("Controle de produção")
    producao_diaria, producao_horaria = preparar_producao(dados_periodo)
    desempenho = calcular_desempenho(dados_periodo, producao_diaria)

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
                template=tema_grafico, labels={"dia": "Dia", "producao": "Peças"}
            )
            aplicar_estilo_grafico(grafico_diario, fundo_grafico, exibir_grade, min(altura_grafico, 520), cor_texto_legenda, cor_rotulos_categoria)
            grafico_diario.update_traces(
                name="Produção diária",
                showlegend=exibir_legenda,
                marker_color=cores_variaveis.get("piece_counter", "#2f80ed"),
            )
            grafico_diario.update_layout(showlegend=exibir_legenda)
            st.plotly_chart(grafico_diario, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes para produção diária.")

    with direita:
        st.markdown("### Produção por hora")
        if not producao_horaria.empty and px is not None:
            grafico_horario = px.bar(
                producao_horaria, x="hora", y="producao", text_auto=True,
                template=tema_grafico, labels={"hora": "Hora", "producao": "Peças"}
            )
            aplicar_estilo_grafico(grafico_horario, fundo_grafico, exibir_grade, min(altura_grafico, 520), cor_texto_legenda, cor_rotulos_categoria)
            grafico_horario.update_traces(
                name="Produção horária",
                showlegend=exibir_legenda,
                marker_color=cores_variaveis.get("piece_counter", "#2f80ed"),
            )
            grafico_horario.update_layout(showlegend=exibir_legenda)
            st.plotly_chart(grafico_horario, use_container_width=True)
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
            facet_row="variavel_amigavel", template=tema_grafico,
            labels={"timestamp": "Horário", "value": "Valor"}
        )
        grafico_series.update_yaxes(matches=None)
        aplicar_estilo_grafico(grafico_series, fundo_grafico, exibir_grade, max(altura_grafico, 520), cor_texto_legenda, cor_rotulos_categoria)
        grafico_series.update_layout(
            showlegend=exibir_legenda,
            legend={"font": {"color": cor_texto_legenda}, "orientation": "h", "y": 1.04, "x": 0},
        )
        grafico_series.for_each_trace(
            lambda trace: trace.update(
                line={"color": cores_variaveis.get(trace.name, "#2f80ed")},
                marker={"color": cores_variaveis.get(trace.name, "#2f80ed")},
            )
        )
        st.plotly_chart(grafico_series, use_container_width=True)
    else:
        st.info("Adicione temperatura, pressão ou tempo de ciclo para visualizar séries temporais.")

    st.caption(str(desempenho["observacao"]))

with aba_analise:
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
                template=tema_grafico, labels={"value": "Valor", "variavel_amigavel": "Variável"}
            )
            aplicar_estilo_grafico(histograma, fundo_grafico, exibir_grade, min(altura_grafico, 520), cor_texto_legenda, cor_rotulos_categoria)
            histograma.update_layout(legend_title_text="")
            st.plotly_chart(histograma, use_container_width=True)
    with direita:
        st.markdown("### Leituras por variável")
        contagens = dados["variavel_amigavel"].value_counts().reset_index()
        contagens.columns = ["Variável", "Quantidade"]
        if px is not None:
            barras = px.bar(contagens, x="Variável", y="Quantidade", color="Quantidade", template=tema_grafico)
            aplicar_estilo_grafico(barras, fundo_grafico, exibir_grade, min(altura_grafico, 520), cor_texto_legenda, cor_rotulos_categoria)
            barras.update_layout(coloraxis_showscale=False)
            st.plotly_chart(barras, use_container_width=True)

with aba_alertas:
    st.subheader("Central de alertas")
    if isinstance(alertas, list) and alertas:
        tabela_alertas = pd.DataFrame(alertas)
        st.warning(f"{len(tabela_alertas)} alerta(s) registrado(s) no histórico JSON.")
        st.dataframe(tabela_alertas, use_container_width=True, hide_index=True)
    else:
        st.success("Nenhum alerta operacional registrado.")

    st.subheader("Anomalias detectadas")
    if "is_anomaly" in dados.columns:
        anomalias = dados[dados["is_anomaly"].astype(str).str.lower().isin(["true", "1"])]
        if anomalias.empty:
            st.info("Nenhuma anomalia foi marcada no CSV atual.")
        else:
            st.dataframe(anomalias.tail(50), use_container_width=True, hide_index=True)
    else:
        st.info("A coluna de anomalia ainda não está presente na telemetria.")

with aba_dados:
    st.subheader("Estado atual da máquina")
    esquerda, direita = st.columns(2)
    with esquerda:
        st.json(estado if estado else {"mensagem": "Estado ainda não disponível"})
    with direita:
        st.json(indicadores if indicadores else {"mensagem": "Indicadores ainda não disponíveis"})
    st.subheader("Telemetria completa")
    st.dataframe(dados.tail(200), use_container_width=True, hide_index=True)

st.caption("Dimensional MES • Protótipo acadêmico de monitoramento e análise industrial")
