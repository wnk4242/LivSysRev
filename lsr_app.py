# lsr_app.py

import os
import shutil
import json
import streamlit as st
import pandas as pd
from datetime import date

from lsr_core import (
    normalize_and_import_csv,
    resolve_bibliographic_columns
)

import plotly.graph_objects as go
# =========================
# PATH CONFIG
# =========================

PROJECT_ROOT = "projects"
os.makedirs(PROJECT_ROOT, exist_ok=True)

# =========================
# SYSTEMATIC REVIEW STAGES
# =========================

STAGES = [
    "Study identification",
    "Title/abstract screening",
    "Full-text screening",
    "Data extraction"
]

STAGE_STATUSES = ["Not started", "In progress", "Completed"]


def project_path(name):
    return os.path.join(PROJECT_ROOT, name)

def csv_path(name):
    return os.path.join(project_path(name), "data.csv")

def count_rows(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return len(pd.read_csv(path))
    return 0


def stage_csv_path(project, stage):
    mapping = {
        "Title/abstract screening": "title_abstract.csv",
        "Full-text screening": "full_text.csv",
        "Data extraction": "data_extraction.csv"
    }
    return os.path.join(project_path(project), mapping[stage])


def metadata_path(name):
    return os.path.join(project_path(name), "metadata.json")

def build_sankey_from_counts(identified, ta, ft, de):
    labels = [
        "Records identified",
        "Title/Abstract screening",
        "Full-text screening",
        "Data extraction",
    ]

    # Flow: Identified → TA → FT → DE
    source = [0, 1, 2]
    target = [1, 2, 3]

    value = [
        identified,  # Records identified → Title/Abstract
        ta,          # Title/Abstract → Full-text
        ft,          # Full-text → Data extraction
    ]

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node=dict(
                    pad=20,
                    thickness=20,
                    line=dict(color="gray", width=0.5),
                    label=labels,
                ),
                link=dict(
                    source=source,
                    target=target,
                    value=value,
                ),
            )
        ]
    )

    fig.update_layout(
        height=350,
        margin=dict(l=20, r=20, t=30, b=20),
    )

    return fig


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
    "Document, standardize, and track database searches "
    "for living systematic reviews."
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

# -------------------------
# Load + initialize metadata (MUST COME FIRST)
# -------------------------

csv_file = csv_path(project)
metadata = load_metadata(project)

metadata.setdefault("stage_status", {})
for stage in STAGES:
    metadata["stage_status"].setdefault(stage, "Not started")

save_metadata(project, metadata)

# =========================
# PROJECT PROGRESS DASHBOARD
# =========================

st.subheader("📊 Project Status")

# ---- Load + initialize metadata ----
metadata = load_metadata(project)
metadata.setdefault("stage_status", {})

for stage in STAGES:
    metadata["stage_status"].setdefault(stage, "Not started")

save_metadata(project, metadata)

base_path = project_path(project)

counts = {
    "Title/abstract screening": count_rows(os.path.join(base_path, "title_abstract.csv")),
    "Full-text screening": count_rows(os.path.join(base_path, "full_text.csv")),
    "Data extraction": count_rows(os.path.join(base_path, "data_extraction.csv")),
}

# ---- Table header ----
col_stage, col_records, col_status = st.columns([3, 1.2, 4])
with col_stage:
    st.markdown("**Stage**")
with col_records:
    st.markdown("**Records**")
with col_status:
    st.markdown("**Status**")

# ---- Table rows ----
for stage in STAGES:
    col_stage, col_records, col_status = st.columns([3, 1.2, 4])

    with col_stage:
        st.markdown(stage)

    with col_records:
        if stage == "Study identification":
            st.markdown("—")  # or "NA"
        else:
            st.markdown(str(counts.get(stage, 0)))

    with col_status:
        status = metadata["stage_status"][stage]

        status_icon = {
            "Not started": "⚪",
            "In progress": "🟡",
            "Completed": "🟢"
        }[status]

        if st.button(f"{status_icon} {status}", key=f"status_{stage}"):
            next_status = {
                "Not started": "In progress",
                "In progress": "Completed",
                "Completed": "Not started"
            }[status]

            metadata["stage_status"][stage] = next_status
            save_metadata(project, metadata)
            st.rerun()


# =========================
# STUDY IDENTIFICATION (LIVING DOCUMENT)
# =========================

st.subheader("📘 Study Identification")

metadata = load_metadata(project)
study_id = metadata.setdefault("study_identification", {})
history = study_id.setdefault("history", [])
current = study_id.setdefault("current", {})

with st.expander("Edit study identification (living document)", expanded=not bool(current)):

    title = st.text_input(
        "Working review title",
        value=current.get("title", "")
    )

    research_question = st.text_area(
        "Primary research question",
        value=current.get("research_question", ""),
        height=80
    )

    population = st.text_input(
        "Population",
        value=current.get("population", "")
    )

    intervention = st.text_input(
        "Intervention / Exposure",
        value=current.get("intervention", "")
    )

    comparator = st.text_input(
        "Comparator (if applicable)",
        value=current.get("comparator", "")
    )

    outcomes = st.text_input(
        "Outcome(s)",
        value=current.get("outcomes", "")
    )

    study_designs = st.text_input(
        "Study designs included",
        value=current.get("study_designs", "")
    )

    inclusion = st.text_area(
        "Inclusion criteria",
        value=current.get("inclusion", ""),
        height=120
    )

    exclusion = st.text_area(
        "Exclusion criteria",
        value=current.get("exclusion", ""),
        height=120
    )

    notes = st.text_area(
        "Notes / rationale (optional)",
        value=current.get("notes", ""),
        height=100
    )

    # ---- Buttons row (INSIDE expander) ----
    col_save, col_download = st.columns([1, 1])

    with col_save:
        if st.button("💾 Save new version"):
            new_version = len(history) + 1
            snapshot = {
                "version": new_version,
                "saved_at": date.today().isoformat(),
                "data": {
                    "title": title,
                    "research_question": research_question,
                    "population": population,
                    "intervention": intervention,
                    "comparator": comparator,
                    "outcomes": outcomes,
                    "study_designs": study_designs,
                    "inclusion": inclusion,
                    "exclusion": exclusion,
                    "notes": notes,
                }
            }

            history.append(snapshot)
            study_id["current"] = snapshot["data"]
            save_metadata(project, metadata)
            st.success(f"Saved version v{new_version}")
            st.rerun()

    with col_download:
        if study_id.get("current"):
            current_data = study_id["current"]
            version_num = len(history)
            last_updated = history[-1]["saved_at"]

            export_text = f"""Study Identification & Review Framing
=================================

Working review title:
{current_data.get("title", "")}

Primary research question:
{current_data.get("research_question", "")}

Population:
{current_data.get("population", "")}

Intervention / Exposure:
{current_data.get("intervention", "")}

Comparator:
{current_data.get("comparator", "")}

Outcome(s):
{current_data.get("outcomes", "")}

Study designs included:
{current_data.get("study_designs", "")}

---------------------------------
Inclusion criteria:
{current_data.get("inclusion", "")}

---------------------------------
Exclusion criteria:
{current_data.get("exclusion", "")}

---------------------------------
Notes / rationale:
{current_data.get("notes", "")}

---------------------------------
Version: v{version_num}
Last updated: {last_updated}
"""

            st.download_button(
                label="⬇ Download (TXT)",
                data=export_text,
                file_name=f"{project}_study_identification_v{version_num}.txt",
                mime="text/plain"
            )


# =========================
# SEARCH DOCUMENTATION
# =========================

st.subheader("🔎 Reference Searches")

with st.expander("Register reference search", expanded=False):

    database_name = st.text_input(
        "Enter a database searched",
        placeholder="e.g., PubMed",
        help="Enter one database name at a time."
    )

    search_strategy = st.text_area(
        "Enter the search query you used (verbatim)",
        height=120
    )

    csv_purpose = st.selectbox(
        "This CSV is imported for:",
        [
            "Title/abstract screening",
            "Full-text screening",
            "Data extraction"
        ]
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

    st.markdown("### Upload search results (CSV)")

    uploaded_csv = st.file_uploader(
        "Upload CSV exported directly from the database",
        type=["csv"]
    )

    if uploaded_csv and st.button("📥 Import and register records"):
        if not database_name.strip() or not search_strategy.strip():
            st.error("Database name and search strategy are required.")
            st.stop()

        try:
            uploaded_csv.seek(0)
            df_upload = pd.read_csv(uploaded_csv, encoding="utf-8")
        except UnicodeDecodeError:
            uploaded_csv.seek(0)
            df_upload = pd.read_csv(uploaded_csv, encoding="latin-1")

        # Save stage-specific dataset for preview
        df_upload.to_csv(stage_csv_path(project, csv_purpose), index=False)

        # ---- COLUMN DETECTION ----
        colmap = resolve_bibliographic_columns(df_upload)

        st.markdown("### 🔍 Detected bibliographic fields")

        preview_rows = []
        for field in ["title", "abstract", "journal", "year"]:
            preview_rows.append({
                "Canonical field": field,
                "Detected column": colmap[field] or "❌ Not detected"
            })

        st.table(pd.DataFrame(preview_rows))

        # ---- MANUAL OVERRIDE ----
        st.markdown("### 🛠 Manual column override (if needed)")

        available_columns = ["— None —"] + list(df_upload.columns)
        override = {}

        for field in ["title", "abstract", "journal", "year"]:
            override[field] = st.selectbox(
                f"{field.capitalize()} column",
                options=available_columns,
                index=(
                    available_columns.index(colmap[field])
                    if colmap[field] in available_columns
                    else 0
                ),
                key=f"override_{field}"
            )


        def resolve_final(auto, manual):
            if manual and manual != "— None —":
                return manual
            return auto


        title_col = resolve_final(colmap["title"], override["title"])
        abstract_col = resolve_final(colmap["abstract"], override["abstract"])
        journal_col = resolve_final(colmap["journal"], override["journal"])
        year_col = resolve_final(colmap["year"], override["year"])

        # ---- VALIDATION ----
        if not title_col:
            st.error("A title column is required to import records.")
            st.stop()

        if not abstract_col:
            st.warning("No abstract column selected. Records will be imported without abstracts.")

        # ---- RENAME ----
        rename = {title_col: "title"}

        if abstract_col:
            rename[abstract_col] = "abstract"
        if journal_col:
            rename[journal_col] = "journal"
        if year_col:
            rename[year_col] = "year"

        df_upload = df_upload.rename(columns=rename)

        for col in ["journal", "year", "abstract"]:
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
            "import_stage": csv_purpose
        })

        save_metadata(project, metadata)

        st.success(f"Imported {added} new records (search {search_id}).")
        st.rerun()


# =========================
# SEARCH HISTORY
# =========================

st.subheader("📜 Reference Search History")

searches = metadata.get("searches", [])

if not searches:
    st.info("No searches documented yet.")
else:
    # Convert search history to a table-friendly format
    history_rows = []

    for s in searches:
        history_rows.append({
            "Stage": s.get("import_stage"),
            "Database": s.get("database"),
            "Date": s.get("run_date"),
            "Coverage": f"{s.get('search_start_year')}–{s.get('search_end_year')}",
            "Records identified": s.get("records_added"),
            "Search query (verbatim)": s.get("search_strategy"),
        })

    df_history = pd.DataFrame(history_rows)

    st.dataframe(
        df_history,
        use_container_width=True,
        hide_index=True
    )

# =========================
# STUDY FLOW OVERVIEW
# =========================

st.subheader("📈 Study Flow Overview")

# Total records identified across all searches
identified = sum(
    s.get("records_added", 0)
    for s in metadata.get("searches", [])
)

ta_count = count_rows(stage_csv_path(project, "Title/abstract screening"))
ft_count = count_rows(stage_csv_path(project, "Full-text screening"))
de_count = count_rows(stage_csv_path(project, "Data extraction"))

if identified > 0:
    fig = build_sankey_from_counts(
        identified=identified,
        ta=ta_count,
        ft=ft_count,
        de=de_count,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No study flow available yet. Import search results to begin.")


# =========================
# RECORD PREVIEW
# =========================

st.subheader("🗐 Record Preview by Screening Stage")

tab1, tab2, tab3 = st.tabs([
    "Title/Abstract Screening",
    "Full-Text Screening",
    "Data Extraction"
])

def preview_stage(tab, stage, empty_msg):
    path = stage_csv_path(project, stage)
    with tab:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            df_stage = pd.read_csv(path)
            st.dataframe(
                df_stage.head(50),
                use_container_width=True,
                height=400
            )
        else:
            st.info(empty_msg)

preview_stage(
    tab1,
    "Title/abstract screening",
    "No records imported yet for title/abstract screening."
)

preview_stage(
    tab2,
    "Full-text screening",
    "No records imported yet for full-text screening."
)

preview_stage(
    tab3,
    "Data extraction",
    "No records imported yet for data extraction."
)



# -------------------------
# Download standardized dataset
# -------------------------

csv_file = csv_path(project)

if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
    df_all = pd.read_csv(csv_file)

    st.download_button(
        "⬇ Download standardized dataset",
        df_all.to_csv(index=False),
        file_name=f"{project}_standardized_records.csv",
        mime="text/csv"
    )
