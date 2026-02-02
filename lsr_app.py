import os
import shutil
import streamlit as st
import pandas as pd
from datetime import date
import json

from lsr_core import (
    search_pubmed,
    fetch_pubmed_records_fast,
    search_openalex,
    update_lsr_database
)

# =========================
# PATH CONFIG
# =========================

PROJECT_ROOT = "projects"
os.makedirs(PROJECT_ROOT, exist_ok=True)

def project_path(name):
    return os.path.join(PROJECT_ROOT, name)

def csv_path(name):
    return os.path.join(project_path(name), "data.csv")

def metadata_path(project):
    return os.path.join(project_path(project), "metadata.json")

def delete_project(project):
    path = project_path(project)
    if os.path.exists(path):
        shutil.rmtree(path)

# =========================
# METADATA
# =========================

def load_metadata(project):
    path = metadata_path(project)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_metadata(project, data):
    path = metadata_path(project)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def list_projects():
    return sorted([
        p for p in os.listdir(PROJECT_ROOT)
        if os.path.isdir(os.path.join(PROJECT_ROOT, p))
    ])

# =========================
# STREAMLIT SETUP
# =========================

st.set_page_config(
    page_title="Living Systematic Review Manager",
    layout="centered"
)

st.title("📚 Living Systematic Review Manager")
st.write(
    "Manage multiple living systematic reviews from beginning to end."
)

# =========================
# SIDEBAR: PROJECTS
# =========================

st.sidebar.header("📁 Projects")

projects = list_projects()

if "current_project" not in st.session_state:
    st.session_state.current_project = None

# Existing projects with delete menu
for p in projects:
    col1, col2 = st.sidebar.columns([0.85, 0.15])

    if col1.button(p, key=f"open_{p}"):
        st.session_state.current_project = p
        st.rerun()

    if col2.button("⋮", key=f"menu_{p}"):
        st.session_state.project_to_manage = p

# Project management menu
if "project_to_manage" in st.session_state:
    p = st.session_state.project_to_manage

    st.sidebar.markdown("---")
    st.sidebar.warning(f"⚠ Manage project: **{p}**")

    if st.sidebar.button("🗑 Delete project"):
        st.session_state.confirm_delete = p

    if st.sidebar.button("Cancel"):
        del st.session_state.project_to_manage

# Delete confirmation
if "confirm_delete" in st.session_state:
    p = st.session_state.confirm_delete

    st.sidebar.error(
        f"❗ This will permanently delete **{p}**.\n\n"
        "This action cannot be undone."
    )

    if st.sidebar.button("❌ Yes, permanently delete"):
        delete_project(p)

        if st.session_state.current_project == p:
            st.session_state.current_project = None

        del st.session_state.confirm_delete
        del st.session_state.project_to_manage
        st.sidebar.success("Project deleted.")
        st.rerun()

    if st.sidebar.button("Cancel deletion"):
        del st.session_state.confirm_delete

st.sidebar.divider()

# Create new project
st.sidebar.subheader("➕ New Project")

new_project_name = st.sidebar.text_input(
    "Project name",
    placeholder="e.g., Living Systematic Review"
)

if st.sidebar.button("Create Project"):
    if not new_project_name.strip():
        st.sidebar.error("Please enter a project name.")
    else:
        path = project_path(new_project_name)
        if os.path.exists(path):
            st.sidebar.error("Project already exists.")
        else:
            os.makedirs(path)
            st.session_state.current_project = new_project_name
            st.sidebar.success("Project created.")
            st.rerun()

# =========================
# MAIN PANEL
# =========================

if not st.session_state.current_project:
    st.info("👈 Select or create a project to begin.")
    st.stop()

project = st.session_state.current_project
st.subheader(f"📂 Current Project: `{project}`")

metadata = load_metadata(project)
query_history = metadata.get("query_history", [])
last_query = metadata.get("last_query", "")

csv_file = csv_path(project)

# =========================
# SEARCH STRATEGY
# =========================

st.subheader("1️⃣ Search Strategy")

database_choice = st.selectbox(
    "Database",
    ["pubmed", "openalex"]
)


if database_choice == "pubmed":
    query = st.text_area(
        "Paste PubMed query (DO NOT include date limits):",
        height=220,
        value=last_query
    )

elif database_choice == "openalex":
    st.caption("Structured Boolean search (OpenAlex)")

    openalex_query = st.text_input(
        "Title & Abstract search (OpenAlex syntax)",
        placeholder='e.g., "sexual assault adolescent"'
    )

st.caption("📜 Search history")

if query_history:
    selected_query = st.selectbox(
        "Previous PubMed queries",
        options=["(Select a previous query)"] + query_history
    )
    if selected_query != "(Select a previous query)":
        query = selected_query
else:
    st.info("No previous searches for this project yet.")

# ---- DOWNLOAD PUBMED SEARCH STRATEGY ----
if last_query:
    pubmed_search_txt = (
        f"Database: PubMed\n"
        f"Search date: {metadata.get('last_run_date', 'NA')}\n"
        f"Time window: {metadata.get('last_search_start_year', 'NA')}–"
        f"{metadata.get('last_search_end_year', 'NA')}\n\n"
        f"Search strategy:\n{last_query}"
    )

    st.download_button(
        label="⬇ Download PubMed search strategy (.txt)",
        data=pubmed_search_txt,
        file_name=f"{project}_pubmed_search.txt",
        mime="text/plain",
    )

# =========================
# TIME WINDOW
# =========================

st.subheader("2️⃣ Time Window")

c1, c2 = st.columns(2)

with c1:
    start_year = st.number_input(
        "Start year",
        min_value=1900,
        max_value=date.today().year,
        value=metadata.get("last_search_start_year", 2000),
        step=1
    )

with c2:
    end_year = st.number_input(
        "End year",
        min_value=1900,
        max_value=date.today().year,
        value=metadata.get("last_search_end_year", date.today().year),
        step=1
    )

# =========================
# RUN SEARCH
# =========================

st.subheader("3️⃣ Run Search")

if st.button("▶ Run Search"):

    if start_year > end_year:
        st.error("❌ Start year must be earlier than or equal to end year.")
        st.stop()

    # =========================
    # PUBMED SEARCH
    # =========================
    if database_choice == "pubmed":

        if not query.strip():
            st.error("❌ Search query cannot be empty.")
            st.stop()

        if query not in query_history:
            query_history.append(query)

        metadata.setdefault("pubmed_searches", []).append({
            "database": "pubmed",
            "search_strategy": query,
            "search_start_year": start_year,
            "search_end_year": end_year,
            "run_date": pd.Timestamp.today().strftime("%Y-%m-%d"),
        })

        save_metadata(project, metadata)

        with st.spinner("🔎 Searching PubMed..."):
            pmids, total_hits = search_pubmed(
                query,
                retmax=100,
                start_year=start_year,
                end_year=end_year
            )

        st.success(f"PubMed returned {total_hits} total hits.")
        st.write(f"PMIDs retrieved in this run: **{len(pmids)}**")

        with st.spinner("📥 Fetching abstracts (XML → PIP fallback)..."):
            records = fetch_pubmed_records_fast(pmids)

        with st.spinner("🧠 Updating project database..."):
            update_lsr_database(
                records,
                project_csv=csv_file,
                search_start_year=start_year,
                search_end_year=end_year
            )

    # =========================
    # OPENALEX SEARCH
    # =========================
    elif database_choice == "openalex":

        with st.spinner("🔎 Searching OpenAlex..."):
            if not openalex_query.strip():
                st.error("❌ OpenAlex search query cannot be empty.")
                st.stop()

            records, total_hits = search_openalex(
                query=openalex_query,
                start_year=start_year,
                end_year=end_year
            )

        st.success(f"OpenAlex returned {total_hits} records.")

        with st.spinner("🧠 Updating project database..."):
            update_lsr_database(
                records,
                project_csv=csv_file,
                search_start_year=start_year,
                search_end_year=end_year
            )

    st.success("🎉 Search completed successfully.")
    st.rerun()


# =========================
# PUBMED SEARCH HISTORY
# =========================

st.subheader("📜 PubMed Search History")

pubmed_history = metadata.get("pubmed_searches", [])

if not pubmed_history:
    st.info("No PubMed searches recorded yet.")
else:
    for i, entry in enumerate(pubmed_history, start=1):
        with st.expander(f"PubMed Search #{i} — {entry['run_date']}"):
            txt = (
                f"Database: PubMed\n"
                f"Search date: {entry['run_date']}\n"
                f"Time window: {entry['search_start_year']}–"
                f"{entry['search_end_year']}\n\n"
                f"Search strategy:\n{entry['search_strategy']}"
            )

            st.markdown(f"**Database:** PubMed")
            st.markdown(f"**Search date:** {entry['run_date']}")
            st.markdown(
                f"**Time window:** {entry['search_start_year']}–{entry['search_end_year']}"
            )
            st.markdown("**Search strategy:**")
            st.markdown(entry["search_strategy"])

            st.download_button(
                label="⬇ Download search strategy (.txt)",
                data=txt,
                file_name=f"{project}_pubmed_search_{i}.txt",
                mime="text/plain",
            )

# =========================
# MANUAL CSV IMPORT
# =========================

from lsr_core import normalize_and_import_csv

st.subheader("📥 Manual Import (Licensed Databases)")

st.caption(
    "Upload CSV files exported from PsycINFO, Embase, Scopus, etc. "
    "Search strategies must be provided for transparency."
)
# ---- SELECT DATABASE SOURCE ----
database_name = st.selectbox(
    "Source database",
    options=[
        "psycinfo",
        "embase",
        "scopus",
        "web_of_science",
        "other"
    ]
)
# ---- Search strategy ----
manual_search_terms = st.text_area(
    "Search strategy (e.g., MeSH or database syntax)",
    height=120,
    placeholder='(MH "Depression") AND (MH "Cognitive Behavioral Therapy")'
)

# ---- Time window ----
c1, c2 = st.columns(2)
with c1:
    manual_start_year = st.number_input(
        "Search start year (manual import)",
        min_value=1900,
        max_value=date.today().year,
        value=metadata.get("last_manual_start_year", 2000),
    )
with c2:
    manual_end_year = st.number_input(
        "Search end year (manual import)",
        min_value=1900,
        max_value=date.today().year,
        value=metadata.get("last_manual_end_year", date.today().year),
    )

# ---- CSV upload ----
uploaded_csv = st.file_uploader(
    "Upload CSV file",
    type=["csv"],
    key="manual_csv_upload"
)

if uploaded_csv and st.button("📤 Import CSV into project"):

    if not manual_search_terms.strip():
        st.error("Please enter the search strategy used.")
        st.stop()

    # ---------- SAFE CSV READ (handle encoding + streamlit file pointer) ----------
    try:
        uploaded_csv.seek(0)
        df_upload = pd.read_csv(uploaded_csv, encoding="utf-8")
    except UnicodeDecodeError:
        uploaded_csv.seek(0)
        df_upload = pd.read_csv(uploaded_csv, encoding="latin-1")


    # ---------- FLEXIBLE COLUMN DETECTION & STANDARDIZATION ----------

    def normalize_colname(c):
        return c.lower().replace(" ", "").replace("_", "")


    normalized_cols = {
        normalize_colname(c): c for c in df_upload.columns
    }

    # ---- Aliases ----
    TITLE_ALIASES = {
        "title",
        "documenttitle",
        "articletitle",
        "ti",
    }

    ABSTRACT_ALIASES = {
        "abstract",
        "abastract",  # PsycINFO typo
        "ab",
        "summary",
        "description",
    }

    JOURNAL_ALIASES = {
        "journal",
        "publicationname",
        "source",
        "so",
    }

    YEAR_ALIASES = {
        "year",
        "publicationyear",
        "py",
    }

    # ---- Detect columns ----
    title_col = None
    abstract_col = None
    journal_col = None
    year_col = None

    for key, original in normalized_cols.items():
        if key in TITLE_ALIASES:
            title_col = original
        elif key in ABSTRACT_ALIASES:
            abstract_col = original
        elif key in JOURNAL_ALIASES:
            journal_col = original
        elif key in YEAR_ALIASES:
            year_col = original

    # ---- Validate required fields ----
    if not title_col or not abstract_col:
        st.error(
            "Could not detect required title and abstract columns.\n\n"
            f"Detected columns: {list(df_upload.columns)}\n\n"
            "Ensure the CSV includes title and abstract fields."
        )
        st.stop()

    # ---- Standardize column names ----
    rename_map = {
        title_col: "title",
        abstract_col: "abstract",
    }

    if journal_col:
        rename_map[journal_col] = "journal"

    if year_col:
        rename_map[year_col] = "year"

    df_upload = df_upload.rename(columns=rename_map)

    # ---- Ensure optional columns exist ----
    if "journal" not in df_upload.columns:
        df_upload["journal"] = None

    if "year" not in df_upload.columns:
        df_upload["year"] = None

    added, round_num = normalize_and_import_csv(
        uploaded_df=df_upload,
        project_csv=csv_file,
        database_name=database_name,
        search_start_year=manual_start_year,
        search_end_year=manual_end_year,
    )

    # ---- SAVE METADATA ----
    metadata.setdefault("manual_imports", []).append({
        "database": database_name,
        "search_strategy": manual_search_terms,
        "search_start_year": manual_start_year,
        "search_end_year": manual_end_year,
        "run_date": date.today().isoformat(),
        "records_added": added,
    })

    metadata["last_manual_start_year"] = manual_start_year
    metadata["last_manual_end_year"] = manual_end_year

    save_metadata(project, metadata)

    st.success(
        f"Manual import completed. Added {added} new records "
        f"(search round {round_num})."
    )

    st.rerun()

# =========================
# MANUAL IMPORT HISTORY
# =========================

st.subheader("📜 Manual Import History")

manual_history = metadata.get("manual_imports", [])

if not manual_history:
    st.info("No manual imports yet.")
else:
    for i, entry in enumerate(manual_history, start=1):
        with st.expander(f"Manual Import #{i} — {entry['run_date']}"):
            st.markdown(f"**Database:** {entry.get('database', 'manual')}")
            st.markdown(f"**Search date:** {entry['run_date']}")
            st.markdown(
                f"**Time window:** {entry['search_start_year']}–{entry['search_end_year']}"
            )

            st.markdown("**Search strategy:**")
            st.markdown(entry["search_strategy"])

            st.markdown(f"**Records added:** {entry['records_added']}")

            manual_txt = (
                f"Database: {entry.get('database', 'manual')}\n"
                f"Search date: {entry['run_date']}\n"
                f"Time window: {entry['search_start_year']}–"
                f"{entry['search_end_year']}\n\n"
                f"Search strategy:\n{entry['search_strategy']}"
            )

            st.download_button(
                label="⬇ Download search strategy (.txt)",
                data=manual_txt,
                file_name=f"{project}_manual_search_{i}.txt",
                mime="text/plain",
            )

# =========================
# PROJECT STATUS
# =========================

st.subheader("4️⃣ Project Status")

if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
    try:
        df = pd.read_csv(csv_file)

        st.write(
            f"**Total records:** {len(df)}  \n"
            f"**Search rounds:** {df['search_round'].max()}"
        )

        st.download_button(
            "⬇ Download Project CSV",
            df.to_csv(index=False),
            file_name=f"{project}_lsr.csv",
            mime="text/csv"
        )
    except pd.errors.EmptyDataError:
        st.info("This project exists but has no records yet.")
else:
    st.info("This project has no records yet.")

# =========================
# RECORD PREVIEW
# =========================

st.subheader("5️⃣ Record Preview")

if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
    try:
        df = pd.read_csv(csv_file)

        preview_cols = [
            "database", "title", "journal", "year",
            "abstract", "search_round", "run_date"
        ]
        cols = [c for c in preview_cols if c in df.columns]

        st.caption(f"Showing first 50 records (out of {len(df)})")

        st.dataframe(
            df[cols].head(50),
            use_container_width=True,
            height=400
        )
    except pd.errors.EmptyDataError:
        st.info("No records to preview yet.")
else:
    st.info("No records to preview yet.")
