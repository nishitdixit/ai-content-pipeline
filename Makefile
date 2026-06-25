.PHONY: demo test ingest clean
demo:
	python examples/run_demo.py
test:
	PYTHONPATH=src python -m unittest discover -s tests -v
clean:
	rm -rf sample_media _staged demo_project src/*.egg-info **/__pycache__
