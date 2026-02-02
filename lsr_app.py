# lsr_app.py

import os
import shutil
import json
import streamlit as st
import pandas as pd
from datetime import date

from lsr_core import normalize_and_import_csv

# =========================
# PATH CONFIG
# =========================

PROJECT_ROOT = "projects"
os.makedirs(PROJECT_ROOT, exist_ok=True)

def project_path(name):
    return os.path.join(PROJECT_ROOT, name)

def csv_path(name):
    return os.path.join(project_path(name), "data.csv")

def metadata_path(name):
    return os.path.join(project_path(name), "metadata.json")

# =========================
# METADATA HELPERS
# =========================

def load_metadata(project):
    path = metadata_path(project)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_metadata(project, data):
    with open(metadata_path(project), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def list_projects():
    return sorted(
        p for p in os.listdir(PROJECT_ROOT)
        if os.path.isdir(os.path.join(PROJECT_ROOT, p))
    )

def delete_project(project):
    shutil.rmtree(project_path(project), ignore_errors=True)

# =========================
# CSV MIGRATION HELPER
# =========================

def load_project_csv_with_migration(csv_file):
    df = pd.read_csv(csv_file)

    # Backward compatibility: search_round → search_id
    if "search_id" not in df.columns and "search_round" in df.columns:
        df = df.rename(columns={"search_round": "search_id"})
        df.to_csv(csv_file, index=False)

    return df

# =========================
# STREAMLIT SETUP
# =========================

st.set_page_config(
    page_title="Living Systematic Review Manager",
    layout="centered"
)

st.title("📚 Living Systematic Review Manager")
st.write(
    "Document, standardize, and track external database searches "
    "for living systematic reviews."
)

st.warning(
    "⚠️ This Streamlit deployment is for demonstration only. "
    "Uploaded data are not guaranteed to persist."
)

# =========================
# SIDEBAR: PROJECTS
# =========================

st.sidebar.header("📁 Projects")

projects = list_projects()

if "current_project" not in st.session_state:
    st.session_state.current_project = None

for p in projects:
    col1, col2 = st.sidebar.columns([0.85, 0.15])
    if col1.button(p, key=f"open_{p}"):
        st.session_state.current_project = p
        st.rerun()
    if col2.button("🗑", key=f"delete_{p}"):
        delete_project(p)
        if st.session_state.current_project == p:
            st.session_state.current_project = None
        st.rerun()

st.sidebar.divider()

new_project = st.sidebar.text_input(
    "➕ New project name",
    placeholder="e.g., Living Depression Review"
)

if st.sidebar.button("Create project"):
    if new_project.strip():
        os.makedirs(project_path(new_project), exist_ok=True)
        st.session_state.current_project = new_project
        st.rerun()

# =========================
# MAIN PANEL
# =========================

if not st.session_state.current_project:
    st.info("👈 Select or create a project to begin.")
    st.stop()

project = st.session_state.current_project
st.subheader(f"📂 Project: `{project}`")

csv_file = csv_path(project)
metadata = load_metadata(project)

# =========================
# SEARCH DOCUMENTATION
# =========================

st.subheader("1️⃣ Register External Search")

database_name = st.text_input(
    "Database searched",
    placeholder="PubMed, PsycINFO, Embase, Scopus, etc."
)

search_strategy = st.text_area(
    "Exact search strategy (verbatim from database)",
    height=120
)

c1, c2 = st.columns(2)
with c1:
    search_start_year = st.number_input(
        "Search start year",
        min_value=1900,
        max_value=date.today().year,
        value=2000
    )
with c2:
    search_end_year = st.number_input(
        "Search end year",
        min_value=1900,
        max_value=date.today().year,
        value=date.today().year
    )

# =========================
# CSV UPLOAD
# =========================

st.subheader("2️⃣ Upload Search Results (CSV)")

uploaded_csv = st.file_uploader(
    "Upload CSV exported directly from the database",
    type=["csv"]
)

if uploaded_csv and st.button("📥 Import records"):

    if not database_name.strip() or not search_strategy.strip():
        st.error("Database name and search strategy are required.")
        st.stop()

    try:
        uploaded_csv.seek(0)
        df_upload = pd.read_csv(uploaded_csv, encoding="utf-8")
    except UnicodeDecodeError:
        uploaded_csv.seek(0)
        df_upload = pd.read_csv(uploaded_csv, encoding="latin-1")

    # ---- COLUMN NORMALIZATION ----
    def norm(c): return c.lower().replace(" ", "").replace("_", "")

    colmap = {norm(c): c for c in df_upload.columns}

    title_col = next((colmap[c] for c in colmap if c in {"title","articletitle","documenttitle","ti"}), None)
    abstract_col = next((colmap[c] for c in colmap if c in {"abstract","ab","summary","description"}), None)
    journal_col = next((colmap[c] for c in colmap if c in {"journal","source","publicationname","so"}), None)
    year_col = next((colmap[c] for c in colmap if c in {"year","py","publicationyear"}), None)

    if not title_col or not abstract_col:
        st.error("CSV must contain title and abstract columns.")
        st.stop()

    rename = {
        title_col: "title",
        abstract_col: "abstract"
    }
    if journal_col:
        rename[journal_col] = "journal"
    if year_col:
        rename[year_col] = "year"

    df_upload = df_upload.rename(columns=rename)

    for col in ["journal", "year"]:
        if col not in df_upload.columns:
            df_upload[col] = None

    added, search_id = normalize_and_import_csv(
        uploaded_df=df_upload,
        project_csv=csv_file,
        database_name=database_name,
        search_start_year=search_start_year,
        search_end_year=search_end_year,
    )

    metadata.setdefault("searches", []).append({
        "database": database_name,
        "search_strategy": search_strategy,
        "search_start_year": search_start_year,
        "search_end_year": search_end_year,
        "run_date": date.today().isoformat(),
        "records_added": added,
        "search_id": search_id
    })

    save_metadata(project, metadata)

    st.success(f"Imported {added} new records (search {search_id}).")
    st.rerun()

# =========================
# SEARCH HISTORY
# =========================

st.subheader("📜 Search History")

searches = metadata.get("searches", [])

if not searches:
    st.info("No searches documented yet.")
else:
    for s in searches:
        with st.expander(f"Search {s['search_id']} — {s['database']}"):
            st.markdown(f"**Date:** {s['run_date']}")
            st.markdown(f"**Time window:** {s['search_start_year']}–{s['search_end_year']}")
            st.markdown("**Search strategy:**")
            st.markdown(s["search_strategy"])
            st.markdown(f"**Records added:** {s['records_added']}")

# =========================
# PROJECT STATUS
# =========================

st.subheader("3️⃣ Project Status")

if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
    df = load_project_csv_with_migration(csv_file)

    st.write(
        f"**Total records:** {len(df)}  \n"
        f"**Searches conducted:** {df['search_id'].max()}"
    )

    st.download_button(
        "⬇ Download standardized dataset",
        df.to_csv(index=False),
        file_name=f"{project}_lsr.csv",
        mime="text/csv"
    )
else:
    st.info("No records imported yet.")

# =========================
# RECORD PREVIEW
# =========================

st.subheader("4️⃣ Record Preview")

if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
    st.dataframe(
        df.head(50),
        use_container_width=True,
        height=400
    )
