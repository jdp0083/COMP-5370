# .SILENT:
# .PHONY: run
# run:
# 	@python deserializer.py $(FILE)

.PHONY: build run

build:
	python -m py_compile deserializer.py

run:
	@python deserializer.py $(FILE)
