# Optional paper figures (requires matplotlib + inputs under artifacts/results or expected/).
.PHONY: paper-rq2-figures
paper-rq2-figures:
	python3 scripts/paper_optional/build_rq2_missed_block_compact.py
