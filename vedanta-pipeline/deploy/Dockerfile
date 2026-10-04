FROM python:3.12-slim
RUN useradd -m vedanta && apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/vedanta
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[google,llm,pdf]"
USER vedanta
VOLUME ["/srv/vedanta/inbox", "/srv/vedanta/out", "/srv/vedanta/state", "/srv/vedanta/secrets"]
CMD ["vedanta", "--config", "/srv/vedanta/config.toml", "run"]
