# Third-party notices

Breachwright depends on third-party open-source software. Those projects remain
under their own licenses. This notice summarizes the direct runtime dependencies
pinned for Breachwright 2.1.0. The package lockfile and Python requirements file
are the source of truth for exact versions and transitive dependencies.

## Python runtime

| Package | License |
| --- | --- |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| SQLAlchemy | MIT |
| aiosqlite | MIT |
| asyncpg | Apache-2.0 |
| Alembic | MIT |
| PyJWT | MIT |
| Passlib | BSD |
| bcrypt | Apache-2.0 |
| Anthropic Python SDK | MIT |
| OpenAI Python SDK | Apache-2.0 |
| Boto3 AWS SDK for Python | Apache-2.0 |
| python-docx | MIT |
| Pydantic | MIT |
| pydantic-settings | MIT |
| python-dotenv | BSD-3-Clause |
| HTTPX | BSD-3-Clause |
| pywebview | BSD-3-Clause |

The resolved Python dependency set also includes packages under MIT,
Apache-2.0, BSD, BSD-3-Clause, MIT-0, MPL-2.0, PSF-2.0, and compatible
dual-license terms.

## Web interface

| Package | License |
| --- | --- |
| React | MIT |
| React DOM | MIT |
| React Router DOM | MIT |
| Recharts | MIT |
| D3 | ISC |
| Lucide React | ISC |

The resolved web dependency set also includes packages under MIT, ISC,
Apache-2.0, BSD-3-Clause, CC-BY-4.0, Unlicense, and compatible combined terms.

## Distribution requirement

Source installations obtain dependencies from their respective package
registries. Packaged desktop or server distributions that bundle dependency
code must also bundle the corresponding license texts from the installed
packages. Release maintainers must regenerate and review the dependency
inventory whenever a dependency or lockfile changes.
