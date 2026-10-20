FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
# Runs over stdio. Set BING_WEBMASTER_API_KEY (and optionally INDEXNOW_KEY) at run time;
# the server starts and lists its tools without a key.
ENTRYPOINT ["bing-webmaster-mcp"]
