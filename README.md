# Genesis

An AI fashion platform with two halves on one core:

- **Consumer** - an AI stylist that builds outfits from real, purchasable items.
- **Enterprise** - a trend and design studio that turns brand DNA plus market
  trend data into trend intelligence and design mockups.

Three documents carry the thinking, and they do different jobs:

- `CLAUDE.md` holds the engineering principles. Read before making structural changes.
- `PLAN.md` holds the architecture and the research behind it.
- `ROADMAP.md` holds the delivery plan: what is next, in what order, and why.

## Local development

Requires Docker, `uv`, and Node.

```sh
cp .env.example .env          # then fill in ANTHROPIC_API_KEY

# Dev database: Postgres 16 with pgvector, matching what runs in production.
docker run -d --name genesis-pg \
  -e POSTGRES_USER=genesis -e POSTGRES_PASSWORD=genesis -e POSTGRES_DB=genesis \
  -p 5434:5432 pgvector/pgvector:pg16

uv sync --extra dev
(cd api && uv run alembic upgrade head)
uv run pytest -q
```

## Hosted database (Neon)

Development runs fine against the local container. Use Neon when something
outside your laptop needs to reach the data, such as a deployed demo.

1. Create a Neon project and copy its connection string.
2. Change the scheme to `postgresql+psycopg` and keep `sslmode=require`.
3. Use the **direct** endpoint, not the `-pooler` one, for migrations: Alembic
   runs DDL in a transaction, which a pooled connection in transaction mode
   cannot hold reliably. Application traffic can use the pooled endpoint.
4. Set `GENESIS_DATABASE_URL` in `.env`, then:

```sh
PYTHONPATH=. uv run python scripts/check_database.py   # connectivity, pgvector, schema
(cd api && uv run alembic upgrade head)
```

## Model access

Model calls go through one gateway; nothing else imports the Anthropic SDK.
`GENESIS_MODEL_PLATFORM` selects where they are served:

| Value | Use |
|---|---|
| `anthropic_api` | Default. No cloud account in the path; prepaid credits with a console spend limit. |
| `claude_platform_aws` | Full API parity, billed through AWS Marketplace. |
| `bedrock_mantle` | AWS as sole data processor, for enterprise security reviews. |

The request body is identical on all three, which is asserted by a test. Only
the model id and the client differ, so switching is configuration.

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
