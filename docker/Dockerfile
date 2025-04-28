# Stage 1: Build dependencies
FROM python:3.11-slim-bookworm AS builder

# Set environment variables
ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_VERSION=1.8.2 \
  POETRY_HOME="/opt/poetry" \
  POETRY_VIRTUALENVS_IN_PROJECT=true \
  POETRY_NO_INTERACTION=1

# System deps for poetry and building some python packages
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
  curl \
  build-essential \
  && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

# Copy only files needed for dependency installation
COPY pyproject.toml poetry.lock* ./

# Install runtime dependencies
# --no-dev: Exclude development dependencies
RUN poetry install --no-dev

# -------------------------------------------------------

# Stage 2: Runtime image
FROM --platform=linux/amd64 python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  # Set path for poetry venv
  PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Add contrib source for ttf-mscorefonts-installer
RUN echo "deb http://deb.debian.org/debian bookworm contrib" >> /etc/apt/sources.list.d/contrib.list

# Accept the EULA for ttf-mscorefonts-installer
RUN echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections

# Install system dependencies required by the application and Chrome
# Combine all installations and cleanup into one RUN command
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
  # Base dependencies
  wget \
  gnupg \
  ca-certificates \
  libpq5 \
  # Fonts
  fonts-liberation \
  ttf-mscorefonts-installer \
  fonts-roboto \
  fonts-noto-core \
  fonts-noto-color-emoji \
  # Chrome dependencies
  libglib2.0-0 \
  libnss3 \
  libgconf-2-4 \
  libfontconfig1 \
  # Add Chrome repo
  && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
  && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
  # Update sources and install Chrome
  && apt-get update \
  && apt-get install -y google-chrome-stable \
  # Clean up
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /etc/apt/sources.list.d/google-chrome.list \
  && rm -f /etc/apt/sources.list.d/contrib.list

# set display port to avoid crash
ENV DISPLAY=:99

# Create a non-root user
RUN groupadd --gid 1001 appuser && \
  useradd --uid 1001 --gid 1001 -m appuser

# Copy virtual environment from builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv

# Copy application code
COPY --chown=appuser:appuser ./app ./app
COPY --chown=appuser:appuser ./templates ./templates
COPY --chown=appuser:appuser ./alembic.ini ./alembic.ini
COPY --chown=appuser:appuser ./alembic ./alembic

# Copy entrypoint script
COPY --chown=appuser:appuser ./docker/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

USER appuser

EXPOSE 8000

# Run entrypoint script by default, running the API
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["api"] 