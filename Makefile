.PHONY: format \
		lint \
		test \
		start-db

start-db:
	docker compose up -d

test: start-db
	uv run pytest --verbose --capture=no --log-cli-level=DEBUG

format:
	uv run ruff format ./src
	uv run ruff check ./src --fix

lint:
	uv lock --check
	uv run mypy ./src
	uv run ruff check ./src
	uv run ruff format ./src --check
