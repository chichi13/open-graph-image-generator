# Open Graph Image Generator

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Open Graph Image Generator** is a Python-based service designed to dynamically generate Open Graph (OG) images for web pages. This helps improve how your links appear when shared on social media platforms like Twitter, Facebook, LinkedIn, etc., by providing custom, informative preview images.

## Features

*   Dynamically generate OG images based on URL parameters or page metadata.
*   Lightweight and deployable using standard Python web servers.
*   Configurable caching and domain whitelisting.
*   Optional asynchronous processing via Celery.
*   Stores generated images in S3-compatible storage.

## Getting Started

### Prerequisites

*   Python 3.10+
*   [Poetry](https://python-poetry.org/) (for dependency management)
*   Access to an S3-compatible object storage service.
*   Access to a PostgreSQL database.
*   Access to a Redis instance

### Installation & Running Locally

1.  **Clone the repository:**

2.  **Install dependencies using Poetry:**
    ```bash
    poetry install
    ```
    *This command installs dependencies listed in `pyproject.toml` into a virtual environment managed by Poetry.*

3.  **Configure environment variables:**
    Copy the example environment file. Populate it with your specific configuration. Refer to `app/config.py` for all available options.
    ```dotenv
    # .env example - Adjust values as needed

    # Basic App Settings
    ENVIRONMENT="development" # development or production
    LOGGING_LEVEL="INFO"

    # Database Settings
    DATABASE_HOST="localhost"
    DATABASE_PORT=5432
    DATABASE_USER="your_db_user"
    DATABASE_PASSWORD="your_db_password"
    DATABASE_NAME="ogimagedb"

    # S3 Storage Settings
    AWS_ACCESS_KEY="YOUR_S3_ACCESS_KEY"
    AWS_SECRET_KEY="YOUR_S3_SECRET_KEY"
    AWS_BUCKET_NAME="your-og-image-bucket"
    # AWS_ENDPOINT_URL="http://localhost:9000" # Uncomment if using MinIO or similar

    REDIS_URL="redis://localhost:6379/1"

    # Celery (Optional)
    # CELERY_ENABLED=True

    # Screenshot Settings
    # SCREENSHOT_DEFAULT_TTL=86400 # Default: 24 hours in seconds
    # ALLOWED_SCREENSHOT_DOMAINS_STR="kactica.com,mystreamagenda.com" # Comma-separated, no spaces if set

    # Contact Email
    CONTACT_EMAIL="your-email@example.com"

    ```

4.  **Run database migrations:**

    ```bash
    poetry run alembic upgrade head
    ```

5.  **Run the application:**
    You can run the Uvicorn server:
    ```bash
    python3 app/main.py
    ```

6.  **Run Celery**
    You can run the Celery Task Queue service by running this command:
    ```bash
    poetry run celery -A app.celery_app worker --loglevel=info -P solo
    ```

The service should now be running at `http://127.0.0.1:8000/`. Find the Swagger documentation at `http://127.0.0.1:8000/docs`.

## Live Testing Instance

A testing instance is available at [https://og.kactica.com](https://og.kactica.com)`.

This instance currently has a whitelist enabled and will only generate images for URLs matching the following domains:

*   kactica.com
*   mystreamagenda.com

You can test it by providing a URL from one of these domains to the generation endpoint (check the API documentation or source code for the exact endpoint structure).

Example: `https://og.kactica.com?url=https://mystreamagenda.com/some-page`

## Contributing

Contributions are welcome! If you'd like to help improve Open Graph Image Generator don't hesitate to open a PR/Issue.

Please ensure your code adheres to the project's coding standards (including type hinting and English language usage).

## License

This project is licensed under the MIT License - see the [LICENSE](https://opensource.org/license/MIT) file for details.