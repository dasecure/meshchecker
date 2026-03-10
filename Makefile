.PHONY: install build wheel clean run test

# Install in development mode
install:
	pip install -e .

# Build wheel and source distribution
build wheel:
	python -m build

# Run the app
run:
	python -m meshcheck.main

# Run tests
test:
	python -m pytest tests/ -v

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	rm -rf __pycache__ src/**/__pycache__

# Build standalone executable
exe:
	pyinstaller --onefile --name meshcheck src/meshcheck/main.py
