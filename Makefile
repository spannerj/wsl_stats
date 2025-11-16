.PHONY: serve run

serve:
	uv run python -m http.server 8000

run:
	uv run python get_data.py
