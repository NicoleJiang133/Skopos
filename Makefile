.PHONY: dev install test check clean

dev:
	SKOPOS_PROVIDER=mock SKOPOS_PERCEPTION=mock python -m uvicorn app:app --host 127.0.0.1 --port 8077 --reload

install:
	python -m pip install -r requirements.txt

test:
	python -m skopos.selftest

check:
	python -m compileall -q skopos

clean:
	rm -rf runs/* __pycache__ skopos/__pycache__
