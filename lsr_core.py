import os
import time
import pandas as pd
from Bio import Entrez
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import feedparser

# =========================
# CONFIG
# =========================

EMAIL = "wnk4242@gmail.com"
Entrez.email = EMAIL

ENTREZ_SLEEP = 0.3
SCRAPE_SLEEP = 0.5

HEADERS = {
    "User-Agent": "Naike_LiveSR/1.0 (email: wnk4242@gmail.com)"
}
# =========================
# OPENALEX CONFIG
# =========================

OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY")
OPENALEX_BASE_URL = "https://api.openalex.org/works"

OPENALEX_HEADERS = {
    "User-Agent": "Naike_LiveSR/1.0"
}

if OPENALEX_API_KEY:
    OPENALEX_HEADERS["Authorization"] = f"Bearer {OPENALEX_API_KEY}"


# =========================
# CANONICAL CSV SCHEMA
# =========================

FINAL_COLUMNS = [
    "database",
    "title",
    "journal",
    "year",
    "abstract",
    "abstract_source",
    "search_round",
    "search_start_year",
    "search_end_year",
    "run_date",
]
# =========================
# PUBMED SEARCH
# =========================

def search_pubmed(query, retmax, start_year, end_year):
    date_filter = f'("{start_year}"[Date - Publication] : "{end_year}"[Date - Publication])'
    full_query = f"{query} AND {date_filter}"

    handle = Entrez.esearch(
        db="pubmed",
        term=full_query,
        retmax=retmax
    )
    record = Entrez.read(handle)
    handle.close()

    pmids = record["IdList"]
    total_hits = int(record["Count"])

    return pmids, total_hits

# =========================
# SAFE PIP SCRAPING
# =========================

def fetch_pubmed_html(pmid):
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    time.sleep(SCRAPE_SLEEP)
    return r.text

def extract_pip_abstract(html):
    soup = BeautifulSoup(html, "html.parser")

    abstract_block = soup.find("section", class_="abstract") \
                     or soup.find("div", class_="abstract")

    if not abstract_block:
        return None, False

    paragraphs = abstract_block.find_all("p")
    if paragraphs:
        text = " ".join(p.get_text(strip=True) for p in paragraphs)
    else:
        text = abstract_block.get_text(separator=" ", strip=True)

    is_pip = text.startswith("PIP:")

    return text, is_pip

# =========================
# FETCH RECORDS
# =========================

def fetch_pubmed_records_fast(pmids, batch_size=50):
    records = []

    batches = [
        pmids[i:i + batch_size]
        for i in range(0, len(pmids), batch_size)
    ]

    for batch in tqdm(batches, desc="XML fetch", unit="batch"):
        handle = Entrez.efetch(
            db="pubmed",
            id=",".join(batch),
            retmode="xml"
        )
        xml = Entrez.read(handle)
        handle.close()

        for art in xml["PubmedArticle"]:
            citation = art["MedlineCitation"]
            article = citation["Article"]

            pmid = str(citation["PMID"])
            title = str(article.get("ArticleTitle"))
            journal = article.get("Journal", {}).get("Title")

            pub_date = article.get("Journal", {}) \
                              .get("JournalIssue", {}) \
                              .get("PubDate", {})
            year = pub_date.get("Year")

            abstract = None
            source = "none"

            if "Abstract" in article:
                abstract = " ".join(
                    str(p) for p in article["Abstract"]["AbstractText"]
                )
                source = "pubmed_xml"

            records.append({
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "year": year,
                "abstract": abstract,
                "abstract_source": source
            })

        time.sleep(ENTREZ_SLEEP)

    # ---------- PIP fallback ----------
    for rec in records:
        if rec["abstract"] is None:
            html = fetch_pubmed_html(rec["pmid"])
            text, is_pip = extract_pip_abstract(html)
            if is_pip:
                rec["abstract"] = text
                rec["abstract_source"] = "pip_web"

    return records

# =========================
# OPENALEX SEARCH
# =========================

def search_openalex(
    title_terms,
    abstract_terms,
    exclude_terms,
    per_page=200,
    max_pages=5
):
    filters = []

    if title_terms:
        filters.append(f"title.search:{'|'.join(title_terms)}")

    if abstract_terms:
        filters.append(f"abstract.search:{'|'.join(abstract_terms)}")

    for t in exclude_terms or []:
        filters.append(f"NOT concepts.display_name:{t}")

    filter_string = ",".join(filters)

    records = []
    cursor = "*"

    for _ in range(max_pages):
        r = requests.get(
            OPENALEX_BASE_URL,
            headers=OPENALEX_HEADERS,
            params={
                "filter": filter_string,
                "per-page": per_page,
                "cursor": cursor
            },
            timeout=30
        )
        r.raise_for_status()
        data = r.json()

        for w in data["results"]:
            records.append({
                "database": "openalex",
                "title": w.get("title"),
                "journal": w.get("host_venue", {}).get("display_name"),
                "year": w.get("publication_year"),
                "abstract": w.get("abstract"),
                "abstract_source": "openalex",
            })

        cursor = data["meta"]["next_cursor"]
        if not cursor:
            break

        time.sleep(0.3)

    return records, len(records)

# =========================
# ARXIV SEARCH
# =========================



def search_arxiv(
    query,
    max_results=200,
    start=0
):
    """
    query: arXiv native query string, e.g.
           (ti:replication OR abs:replication) AND cat:stat.ME
    """

    base_url = "http://export.arxiv.org/api/query"

    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status()

    feed = feedparser.parse(response.text)

    records = []

    for entry in feed.entries:
        year = None
        if hasattr(entry, "published"):
            year = entry.published[:4]

        records.append({
            "database": "arxiv",
            "title": entry.title.strip().replace("\n", " "),
            "journal": "arXiv",
            "year": year,
            "abstract": entry.summary.strip().replace("\n", " "),
            "abstract_source": "arxiv_api",
        })

    return records, len(records)


# =========================
# UPDATE LSR DATABASE
# =========================
def update_lsr_database(records, project_csv, search_start_year, search_end_year):
    run_date = pd.Timestamp.today().strftime("%Y-%m-%d")

    # ---------- SAFE LOAD ----------
    if os.path.exists(project_csv) and os.path.getsize(project_csv) > 0:
        try:
            df_old = pd.read_csv(project_csv)

            next_round = int(df_old["search_round"].max()) + 1
        except pd.errors.EmptyDataError:
            df_old = pd.DataFrame()
            next_round = 1
    else:
        df_old = pd.DataFrame()
        next_round = 1

    # ---------- ADD NEW RECORDS ----------
    new_rows = []

    # deduplicate by title (consistent with manual imports)
    # ---------- SAFE TITLE DEDUP SET ----------
    if "title" in df_old.columns:
        existing_titles = set(
            df_old["title"].astype(str).str.lower().str.strip().dropna()
        )
    else:
        existing_titles = set()

    for r in records:
        title = str(r.get("title", "")).strip()
        if not title:
            continue

        if title.lower() in existing_titles:
            continue

        # ---- REMOVE PMID IF PRESENT ----
        r.pop("pmid", None)

        # ---- MARK SOURCE DATABASE (default pubmed) ----
        r["database"] = r.get("database", "pubmed")

        # ---- LSR METADATA ----
        r["search_round"] = next_round
        r["search_start_year"] = search_start_year
        r["search_end_year"] = search_end_year
        r["run_date"] = run_date

        new_rows.append(r)

    # ---------- WRITE ----------
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_old

    # ---------- FORCE FINAL COLUMN ORDER ----------
    df_all = df_all[[c for c in FINAL_COLUMNS if c in df_all.columns]]

    df_all.to_csv(project_csv, index=False)

    return df_all

# =========================
# MANUAL CSV IMPORT
# =========================

from datetime import date



def normalize_and_import_csv(
    uploaded_df,
    project_csv,
    database_name,
    search_start_year,
    search_end_year,
):
    run_date = date.today().isoformat()

    # ---------- LOAD EXISTING PROJECT ----------
    if os.path.exists(project_csv) and os.path.getsize(project_csv) > 0:
        df_old = pd.read_csv(project_csv)
        next_round = int(df_old["search_round"].max()) + 1

        existing_titles = set(
            df_old["title"].str.lower().str.strip().dropna()
        )
    else:
        df_old = pd.DataFrame(columns=FINAL_COLUMNS)
        next_round = 1
        existing_titles = set()

    new_rows = []

    for _, row in uploaded_df.iterrows():
        title = str(row.get("title", "")).strip()

        if not title:
            continue

        # ---------- DEDUPLICATION ----------


        if title.lower() in existing_titles:
            continue

        new_rows.append({
            "database": database_name,
            "title": title,
            "journal": row.get("journal"),
            "year": row.get("year"),
            "abstract": row.get("abstract"),
            "abstract_source": "csv_import",
            "search_round": next_round,
            "search_start_year": search_start_year,
            "search_end_year": search_end_year,
            "run_date": run_date,
        })

    # ---------- WRITE ----------
    if new_rows:
        df_new = pd.DataFrame(new_rows, columns=FINAL_COLUMNS)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_old

    df_all.to_csv(project_csv, index=False)

    return len(new_rows), next_round
