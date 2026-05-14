# Paper artifact helpers (optional; figures read committed results/*.json only).
.PHONY: paper-rq2-figures
paper-rq2-figures:
	python3 scripts/build_rq2_missed_block_compact.py
