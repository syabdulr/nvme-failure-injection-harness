MAKEFLAGS += --no-print-directory

.PHONY: help setup dev test run scenarios list decode clean

help:
	@echo "targets:"
	@echo "  setup      install qemu / nvme-cli / virtme-ng (uses sudo)"
	@echo "  dev        editable-install Project 1 (nvme-logpage-explorer) from ../"
	@echo "  test       run unit tests (no device needed)"
	@echo "  run        run every scenario in a VM -> output/*.report.md"
	@echo "  scenarios  run only the client-side scenarios (single VM boot)"
	@echo "  list       list scenarios"
	@echo "  decode V=0x4080   decode an NVMe status value"
	@echo "  clean      remove output/ and the backing file"

setup:
	./env/setup.sh

dev:
	pip install --break-system-packages -e ../nvme-logpage-explorer

test:
	python3 -m unittest discover -s tests -v

run:
	./env/run.sh

scenarios:
	./env/run.sh oob_write invalid_opcode compare_mismatch

list:
	python3 harness.py list

decode:
	python3 harness.py decode $(V)

clean:
	rm -rf output env/nvme-backing.raw env/blkdebug-*.conf
