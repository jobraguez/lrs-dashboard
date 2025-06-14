#!/usr/bin/env python3
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import subprocess, sys
import unidecode
from dateutil import parser
from requests.auth import HTTPBasicAuth

# Lê as credenciais do Streamlit Cloud
org_id = st.secrets["lrs"]["org_id"]
user   = st.secrets["lrs"]["user"]
pw     = st.secrets["lrs"]["pass"]

# Monta o HTTPBasicAuth e endpoint base
AUTH     = HTTPBasicAuth(user, pw)
BASE_URL = f"https://watershedlrs.com/watershed/api/organizations/{org_id}/lrs/statements"

# ─── Autenticação ────────────────────────────────────────────────
# define aqui as tuas credenciais (username: password)
CREDENTIALS = {
    "admin": "admin123",
    "learn": "learn123"
}

# 2) Inicialize o estado de sessão
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# 3) Se não estiver autenticado, mostre o formulário de login e pare a execução
if not st.session_state.logged_in:
    st.title("🔒 Por favor faça login")
    user = st.text_input("👤 Utilizador")
    pwd  = st.text_input("🔑 Password", type="password")
    if st.button("Entrar"):
        if CREDENTIALS.get(user) == pwd:
            st.session_state.logged_in = True
            #st.experimental_rerun()  # tento um rerun aqui, mas se der erro basta remover
        else:
            st.error("Utilizador ou password incorretos")
    st.stop()



# ────────────────────────────────────────────────────────────────┘
# ─── 0. Configuração da página ─────────────────────────────────
st.set_page_config(
    page_title="Dashboard Animação 2D",
    layout="wide",
)
from streamlit.runtime.scriptrunner import RerunException, RerunData
if st.button("🔄 Atualizar dados"):
    # chama o export.py com o mesmo interpretador Python
    subprocess.run([sys.executable, "export.py"], check=True)
    # força o Streamlit a reiniciar o script
    raise RerunException(RerunData())
# ─── 1. Constantes ─────────────────────────────────────────────┐
CSV_FILE = "statements_clean.csv"
DIAG_CSV       = 'diagnostica_clean.csv'
FINAL_CSV      = 'final_clean.csv'
SATISF_CSV     = 'satisfacao_clean.csv'
# ────────────────────────────────────────────────────────────────┘

# ─── 2. Carregamento e pré-processamento ───────────────────────┐
@st.cache_data
def load_data():
    df = pd.read_csv(CSV_FILE)
    # 2.1 Timestamp → datetime[ns, UTC]
    df["timestamp"] = (
        df["timestamp"]
        .astype(str)  # garante object
        .apply(lambda s: parser.isoparse(s) if s and s.lower() != "nan" else pd.NaT)
        .dt.tz_convert("UTC")
    )
    # 2.2 Limpa módulo de espaços/brancos invisíveis
    df["module"] = df["module"].astype(str).str.strip()
    # avaliações
    df_diag = pd.read_csv(DIAG_CSV)
    df_final = pd.read_csv(FINAL_CSV)
    df_satis = pd.read_csv(SATISF_CSV)
    return df, df_diag, df_final, df_satis

df, df_diag, df_final, df_satis = load_data()
# Lista de módulos realmente existentes (ordenada)
modules_list = sorted(df["module"].dropna().unique())
# ────────────────────────────────────────────────────────────────┘
def load_satisfacao():
    df = pd.read_csv(SATISF_CSV, encoding="utf8")
    # 1) Concelhos: colunas que começam por “Q05_Concelho”
    concelhos = [c for c in df.columns if c.startswith("Q05_Concelho")]
    # melt para apanhar o concelho com valor True/1
    df_conc = (
        df[["ID"] + concelhos]
        .melt(id_vars="ID", value_vars=concelhos,
              var_name="origem", value_name="flag")
        .query("flag == True or flag == 1")
    )
    df_conc["Concelho"] = df_conc["origem"].str.split("->").str[-1]
    # 2) Escolaridade: colunas que começam por “Q07_Nível”
    escolaridade = [c for c in df.columns if c.startswith("Q07_Nível")]
    df_esc = (
        df[["ID"] + escolaridade]
        .melt(id_vars="ID", value_vars=escolaridade,
              var_name="origem", value_name="flag")
        .query("flag == True or flag == 1")
    )
    df_esc["Escolaridade"] = df_esc["origem"].str.split("->").str[-1]
    # 3) Nacionalidade diretamente
    df_nat = df[["ID", "Q06_Nacionalidade"]].rename(
        columns={"Q06_Nacionalidade": "Nacionalidade"}
    )
    # 4) Junta tudo
    df_demo = (
        df_nat
        .merge(df_conc[["ID", "Concelho"]], on="ID", how="left")
        .merge(df_esc[["ID", "Escolaridade"]], on="ID", how="left")
        .drop(columns="ID")
    )
    return df_demo


# ————————————————————————————————————————————————
# ─── 2. Selector de visão ───────────────────────────────────────
view = st.sidebar.radio(
    "🗂️ Seleciona a Visão",
    ["Visão Admin", "Visão Learn Stats"]
)

# ─── 3. Visão Admin ─────────────────────────────────────────────
if view == "Visão Admin":
    st.title("🔧 Visão Admin")
    # --- Visão Geral ---
    st.header("Visão Geral")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Statements", len(df))
    c2.metric("Total Módulos", df["module"].nunique())
    c3.metric("Total Utilizadores", df["user"].nunique())

    # ─── 4. Statements por Módulo ─────────────────────────────────┐
    st.subheader("📦 Statements por Módulo")

    # Garante zero para módulos sem statements hoje
    mod_counts = df["module"].value_counts().reindex(modules_list, fill_value=0)

    # Tabela
    st.dataframe(
        mod_counts
        .rename_axis("Módulo")
        .reset_index(name="Contagem")
    )

    # Gráfico de barras
    fig, ax = plt.subplots(figsize=(8,4))
    mod_counts.plot.bar(ax=ax)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_xlabel("Módulo")
    ax.set_ylabel("Número de statements")
    plt.xticks(rotation=45, ha='right')
    st.pyplot(fig)
    plt.tight_layout()


    # ────────────────────────────────────────────────────────────────┘


    # ─── 5. Verbos mais comuns ─────────────────────────────────────┐
    st.subheader("🔤 Verbos mais comuns")

    verb_counts = df["verb"].value_counts()
    st.table(
        verb_counts
        .rename_axis("Verbo")
        .reset_index(name="Contagem")
    )
    st.bar_chart(verb_counts)
    # ────────────────────────────────────────────────────────────────┘
    # ─── X. Contagem de Verbos por Módulo ────────────────────────────
    st.subheader("📊 Verbos por Módulo")

    # 1) Pivot table: linhas = módulo, colunas = verbo, valores = contagem
    verbs_of_interest = ["completed","answered","progressed","interacted","attempted"]
    # normaliza tudo para lowercase para evitar duplicados
    df["verb_lc"] = df["verb"].str.lower()

    pivot = (
        df[df["verb_lc"].isin(verbs_of_interest)]
        .groupby(["module","verb_lc"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=verbs_of_interest, fill_value=0)
    )

    # 2) Exibe tabela
    st.table(pivot.rename_axis("Módulo").rename(columns=str.capitalize))

    # 3) Gráfico de barras empilhadas (opcional)
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    pivot.plot(
        kind="bar",
        stacked=True,
        ax=ax2
    )
    ax2.set_xlabel("Módulo")
    ax2.set_ylabel("Contagem de Statements")
    ax2.legend(title="Verbo", bbox_to_anchor=(1.02,1), loc="upper left")
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig2)

    # ─── 7. Evolução Diária de Statements ──────────────────────────┐
    st.subheader("📅 Evolução Diária de Statements")

    # Garante que estamos usando DatetimeIndex
    df_daily = df.set_index("timestamp").resample("D").size()
    st.line_chart(df_daily)
    # ────────────────────────────────────────────────────────────────┘

# ────────────────────────────────────────────────────────────────┘
# ─── 4. Visão Learn Stats ────────────────────────────────────────
else:
    st.title("📊 Visão Learn Stats")

    # ─── 6. Tentativas vs Respondidas por Pergunta (Global) ────────
    st.subheader("❓ Tentativas vs Respondidas por Pergunta (Global)")

    # filtra statements com verbo contendo 'attempt' e 'answer'
    df_attempts = df[df['verb'].str.lower().str.contains('attempt', na=False)]
    df_answered = df[df['verb'].str.lower().str.contains('answer', na=False)]

    # conta tentativas e respondidas por activity
    attempts = df_attempts['activity'].value_counts()
    answered = df_answered['activity'].value_counts()

    # mantém só perguntas que começam por "Pergunta"
    mask = attempts.index.str.startswith("Pergunta")
    attempts = attempts[mask]
    answered = answered.reindex(attempts.index, fill_value=0)

    # prepara DataFrame final
    df_q = pd.DataFrame({
        'Pergunta': attempts.index,
        'Tentativas': attempts.values,
        'Respondida': answered.values
    })

    if df_q.empty:
        st.info("Não há tentativas registadas em perguntas.")
    else:
        # ––––––––– opção 1: usar st.dataframe para ordenação manual no cabeçalho
        #st.dataframe(df_q, use_container_width=True)

        # ––––––––– opção 2: controlo de ordenação via UI
        #st.markdown("**Ordenar tabela**")
        sort_col = st.selectbox("Ordenar por:", ['Pergunta','Tentativas','Respondida'], index=0)
        asc = st.checkbox("Ordem ascendente", value=False)
        df_q_sorted = df_q.sort_values(sort_col, ascending=asc)
        st.dataframe(df_q_sorted, use_container_width=True)

        # gráfico de barras agrupadas (baseado na tabela ordenada)
        fig, ax = plt.subplots(figsize=(10, 5))
        x = range(len(df_q_sorted))
        ax.bar(x, df_q_sorted['Tentativas'], width=0.4, label='Tentativas')
        ax.bar([i+0.4 for i in x], df_q_sorted['Respondida'], width=0.4, label='Respondida')
        ax.set_xticks([i+0.2 for i in x])
        ax.set_xticklabels(df_q_sorted['Pergunta'], rotation=45, ha='right')
        ax.set_xlabel("Pergunta")
        ax.set_ylabel("Contagem")
        ax.legend()
        plt.tight_layout()
        st.pyplot(fig)

    # ─── Avaliações & Satisfação ──────────────────────────
    st.header("📊 Avaliações e Satisfação")

    tabs = st.tabs(["Diagnóstica", "Avaliação Final", "Satisfação"])
    with tabs[0]:
        st.subheader("📝 Avaliação Diagnóstica")
        st.dataframe(df_diag, use_container_width=True)
        # exemplo de gráfico de respostas por questão
        if 'Pergunta' in df_diag.columns and 'Resposta' in df_diag.columns:
            q_counts = df_diag.groupby('Pergunta')['Resposta'].value_counts().unstack(fill_value=0)
            st.bar_chart(q_counts)

    with tabs[1]:
        st.subheader("📝 Avaliação Final")
        st.dataframe(df_final, use_container_width=True)
        if 'Pergunta' in df_final.columns and 'Resposta' in df_final.columns:
            qf_counts = df_final.groupby('Pergunta')['Resposta'].value_counts().unstack(fill_value=0)
            st.bar_chart(qf_counts)

    with tabs[2]:
        st.subheader("🙂 Satisfação do Curso")
        st.dataframe(df_satis, use_container_width=True)
        if 'Pergunta' in df_satis.columns and 'Resposta' in df_satis.columns:
            qs_counts = df_satis.groupby('Pergunta')['Resposta'].value_counts().unstack(fill_value=0)
            st.bar_chart(qs_counts)

    # ————————————————————————————————————————————————
    # 8. Evolução: Diagnóstica vs Final (linha)
    # ————————————————————————————————————————————————

    st.subheader("📈 Evolução: Diagnóstica → Final")

    # 8.1. Carrega os CSVs limpos das avaliações (só têm duas colunas: id_inútil e nota)
    df_diag  = pd.read_csv("diagnostica_clean.csv", encoding="utf8")
    df_final = pd.read_csv("final_clean.csv",      encoding="utf8")

    # 8.2. Extrai a nota, normaliza vírgulas e converte para float
    diag_scores  = (
        df_diag
        .iloc[:, 1]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
        .reset_index(drop=True)
    )
    final_scores = (
        df_final
        .iloc[:, 1]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
        .reset_index(drop=True)
    )

    # 8.3. Ajusta comprimento
    n = min(len(diag_scores), len(final_scores))
    diag_scores  = diag_scores.iloc[:n]
    final_scores = final_scores.iloc[:n]

    # 8.4. DataFrame de evolução
    df_evol = pd.DataFrame({
        "Diagnóstica": diag_scores,
        "Final":      final_scores
    })
    df_evol["Diferença"] = (df_evol["Final"] - df_evol["Diagnóstica"]).round(1)

    # 8.5. Tabela interativa ordenável
    st.dataframe(df_evol, use_container_width=True)

    # 8.6. **Gráfico de Linhas** comparativo
    st.line_chart(df_evol[["Diagnóstica","Final"]])

    import re

    # ————————————————————————————————————————————————
    # 8. Inquérito de Satisfação
    # ————————————————————————————————————————————————



    # 8.1. Carrega dados limpos
    df_sat = pd.read_csv("satisfacao_clean.csv", encoding="utf8")

    # 8.2. Caracterização da Amostra
    # ————————————————————————————————————————————————


    st.header("📝 Inquérito de Satisfação • Caracterização da Amostra")

    df_satis = load_satisfacao()

    #st.subheader("🔹 Tabela de Caracterização")
    #st.dataframe(df_satis)

    # Distribuições
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Distrito")
        st.bar_chart(df_satis["Concelho"].value_counts())
    with col2:
        st.subheader("Nacionalidades")
        st.bar_chart(df_satis["Nacionalidade"].value_counts())
    with col3:
        st.subheader("Escolaridade")
        st.bar_chart(df_satis["Escolaridade"].value_counts())

    # 8.3. Resultados por Pergunta
    st.subheader("📊 Resultados por Pergunta")

    # Seleciona apenas colunas cujo nome comece por 'Q' seguido de dígitos
    q_cols = [c for c in df_sat.columns
              if re.match(r"^Q0[1-3](_|$)", c, re.IGNORECASE)]

    if not q_cols:
        st.warning("Nenhuma coluna de pergunta Q01–Q03 encontrada.")
    else:
        # Converte vírgulas para ponto e força números; erros virão como NaN
        df_qnum = df_sat[q_cols].apply(
            lambda col: pd.to_numeric(
                col.astype(str).str.replace(",", ".", regex=False),
                errors="coerce"
            )
        )
        # Calcula média por pergunta, arredonda a 1 casa decimal
        mean_scores = df_qnum.mean().round(1)

        # Tabela interativa (ordenável)
        df_q = mean_scores.reset_index()
        df_q.columns = ["Pergunta", "Média"]
        st.dataframe(df_q, use_container_width=True)

    # Gráfico de barras
        #st.bar_chart(mean_scores)

    # ─── Tempo Diagnóstica → Satisfação por Usuário ────────────────
    st.subheader("⏱️ Tempo Diagnóstica → Satisfação por Usuário")

    # 1) Normaliza módulo
    df["module_norm"] = (
        df["module"]
        .fillna("")
        .astype(str)
        .apply(unidecode.unidecode)  # tira acentos
        .str.lower()
    )
    # 2) normaliza verbos
    df["verb_lc"] = df["verb"].str.lower()

    # 3) máscaras corretas
    start_mask = (
            (df["verb_lc"] == "viewed") &
            df["module_norm"].str.contains("diagnostica", na=False)
    )
    end_mask = (
            (df["verb_lc"].isin(["submitted", "answered"])) &
            df["module_norm"].str.contains("satisf", na=False)
    )


    # 5) agrupa e intersecta users
    starts = df[start_mask].groupby("user")["timestamp"].min()
    ends = df[end_mask].groupby("user")["timestamp"].max()
    common = starts.index.intersection(ends.index)

    if len(common) == 0:
        st.warning("⚠️ Não há utilizadores com ambos os eventos de início e fim.")
    else:
        # 6) calcula durações em minutos
        durations = ((ends[common] - starts[common]).dt.total_seconds() / 60).round(1)
        avg = round(durations.mean(), 1)

        # 7) mostra resultados
        st.metric("⏲️ Tempo Médio (min)", f"{avg}")
        dur_df = durations.reset_index()
        dur_df.columns = ["Usuário", "Minutos"]
        st.dataframe(dur_df, use_container_width=True)
        st.bar_chart(dur_df.set_index("Usuário")["Minutos"])