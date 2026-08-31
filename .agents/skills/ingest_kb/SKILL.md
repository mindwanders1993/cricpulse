---
name: ingest_kb
description: A universal harvester skill that scrapes and dumps raw interview questions from repositories or web sources into the KaizenCodes Knowledge Base archive.
---

# KaizenCodes Knowledge Base Ingestion Skill (`ingest_kb`)

## 🎯 Purpose
The `ingest_kb` skill acts as a universal, language-agnostic data miner. Its only job is to discover interview questions (SQL, PySpark, Python) from open-source repositories or web links and dump them as raw text/JSON into the KaizenCodes Knowledge Base (`docs/knowledge_base/raw/`).

It does **not** deduplicate, it does **not** reverse-engineer schemas, and it does **not** write code. It simply gathers raw material.

## 🚦 Operational Workflow (Strict Protocol)

When the user invokes this skill (e.g., *"Find more DataLemur SQL questions"* or *"Ingest this repo"*), follow these steps:

### 1. Discover & Catalog
- If the user provides a specific URL or repository, proceed to Step 2.
- If the user provides a general topic (e.g., *"Find FAANG SQL questions"*), use web search tools to locate high-quality open-source GitHub repositories containing relevant questions.
- **Action**: Update `docs/knowledge_base/repo_catalog.md` with the newly discovered repository URL, its star count, and a brief description.

### 2. Extract & Dump
- Scrape the target repository or URL. You may write a temporary Python script or use your built-in tools to read the `.md`, `.sql`, or `.py` files containing the problems.
- Extract the raw problem text, any provided hints, and the raw solution code.
- **Action**: Create a new file in `docs/knowledge_base/raw/` (e.g., `docs/knowledge_base/raw/raw_datalemur_batch_1.json` or `.md`) and dump the extracted data into it. Do not worry about standardizing the schema strictly; just capture the raw text.

### 3. Summarize & Report
- Calculate the total number of raw questions just ingested.
- **Action**: Provide a brief summary to the user: *"Successfully ingested [X] raw questions into `docs/knowledge_base/raw/raw_filename.json`."*
- **Action**: Ask the user: *"Would you like to ingest another source, or should we switch to the `add_sql_question` skill to start adding these to the platform?"*

## ⚠️ Guidelines
- **No Refinement**: Do not attempt to fix broken SQL or rewrite the problem statements. Keep the data raw and pure.
- **Language Agnostic**: This skill should be capable of grabbing `.py`, `.scala`, or `.sql` files equally well.
