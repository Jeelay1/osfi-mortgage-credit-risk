# Rebuild everything from the raw OSFI snapshot.
# Needs PostgreSQL 16; set DATABASE_URL if yours is not postgresql://postgres@localhost:5433/osfi

.PHONY: all data database marts analysis notebook summary docs test

all: database marts analysis notebook summary docs

data:            ## optional: download OSFI's latest files and re-extract M4
	python src/download_data.py
	python src/extract_m4.py

database:
	python src/build_database.py

marts:
	python src/export_marts.py

analysis:
	python src/analysis.py

notebook:
	python src/build_notebook.py

summary:
	python src/build_summary.py

docs:
	python src/build_docs.py

test:
	pytest -q
