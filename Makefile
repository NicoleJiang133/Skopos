.PHONY: dev install test check clean

dev:
	SKOPOS_PROVIDER=mock python -m uvicorn app:app --host 127.0.0.1 --port 8077 --reload

install:
	python -m pip install -r requirements.txt

test:
	python selftest.py

check:
	python -m compileall -q app.py bandit.py privacy.py recorder.py selftest.py providers

clean:
	rm -rf runs/run-* __pycache__ providers/__pycache__
