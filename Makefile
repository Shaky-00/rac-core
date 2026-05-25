# Optional paper figures (requires matplotlib + RAC_TRACEBENCH_ROOT).
.PHONY: paper-rq2-figures paper-rq2 rq2-overlay

paper-rq2-figures:
	python3 scripts/paper_optional/build_rq2_missed_block_compact.py

rq2-overlay:
	python3 scripts/generate_rq2_composite_overlay.py

paper-rq2: rq2-overlay
	bash scripts/run_rq2_tracebench.sh

.PHONY: paper-rq4-overhead paper-overhead-expanded
paper-rq4-overhead paper-overhead-expanded:
	sed -i 's/\r$$//' scripts/run_rq4_expanded_overhead.sh 2>/dev/null || true
	chmod +x scripts/run_rq4_expanded_overhead.sh
	bash scripts/run_rq4_expanded_overhead.sh
