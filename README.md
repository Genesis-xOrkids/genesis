# Genesis

An AI fashion platform with two halves on one core:

- **Consumer** - an AI stylist that builds outfits from real, purchasable items.
- **Enterprise** - a trend and design studio that turns brand DNA plus market
  trend data into trend intelligence and design mockups.

`CLAUDE.md` holds the engineering principles. `PLAN.md` holds the architecture
and research behind them. Read both before making structural changes.

## Local development

Requires Docker, `uv`, and Node.

```sh
# Dev database: Postgres 16 with pgvector, matching Aurora in production.
docker run -d --name genesis-pg \
  -e POSTGRES_USER=genesis -e POSTGRES_PASSWORD=genesis -e POSTGRES_DB=genesis \
  -p 5434:5432 pgvector/pgvector:pg16

uv sync --extra dev
(cd api && uv run alembic upgrade head)
uv run pytest api/tests -q
```

## Checks

```sh
uv run ruff check api/          # lint
uv run ruff format api/         # format
uv run mypy api/genesis_api     # types, strict
uv run pytest api/tests -q      # tests
```

Migration health, per `CLAUDE.md`:

```sh
cd api
uv run alembic heads            # must print exactly one line
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "drift probe"   # diff must be empty
```
