import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from app.config import settings
from app.logger import logger


# --- S3 Client Initialization ---
def get_s3_client():
    """Creates an S3 client based on application settings."""

    s3_config = Config(
        signature_version="s3v4",
        s3={
            "use_accelerate_endpoint": False,
        },
    )

    client_args = {
        "service_name": "s3",
        "aws_access_key_id": settings.AWS_ACCESS_KEY,
        "aws_secret_access_key": settings.AWS_SECRET_KEY,
        "config": s3_config,
    }
    if settings.AWS_ENDPOINT_URL:
        logger.info(f"Using custom S3 endpoint: {settings.AWS_ENDPOINT_URL}")
        client_args["endpoint_url"] = str(settings.AWS_ENDPOINT_URL)

    return boto3.client(**client_args)


s3_client = get_s3_client()


def upload_to_s3(local_file_path: str, destination_s3_key: str) -> str:
    """Uploads a local file to the configured S3 bucket.

    Args:
        local_file_path: The path to the local file to upload.
        destination_s3_key: The desired key (path) for the object in S3.

    Returns:
        The object URL. For AWS S3, this is the standard https URL.
        For custom endpoints, it's constructed based on the endpoint URL.

    Raises:
        FileNotFoundError: If the local file does not exist.
        NoCredentialsError/PartialCredentialsError: If AWS credentials aren't found.
        ClientError: For other S3-related errors during upload.
        Exception: For unexpected errors.
    """
    bucket_name = settings.AWS_BUCKET_NAME
    logger.info(
        f"Attempting to upload {local_file_path} to s3://{bucket_name}/{destination_s3_key}"
    )

    try:
        s3_client.upload_file(
            local_file_path,
            bucket_name,
            destination_s3_key,
            ExtraArgs={
                "ContentType": "image/png",
                "ACL": "public-read",
            },
        )

        # Construct the final access URL, prioritizing CDN_URL if available
        if settings.CDN_URL:
            cdn_base = str(settings.CDN_URL).rstrip("/")
            object_url = f"{cdn_base}/{destination_s3_key}"
            logger.info(f"Using CDN URL: {object_url}")
        elif settings.AWS_ENDPOINT_URL:
            # For custom S3 endpoints without CDN
            endpoint = str(settings.AWS_ENDPOINT_URL).rstrip("/")
            object_url = f"{endpoint}/{bucket_name}/{destination_s3_key}"
            logger.info(f"Using Custom S3 Endpoint URL: {object_url}")
        else:
            # Default to standard AWS S3 URL (virtual-hosted style)
            object_url = f"https://{bucket_name}.s3.amazonaws.com/{destination_s3_key}"
            logger.info(f"Using standard AWS S3 URL: {object_url}")

        return object_url

    except FileNotFoundError:
        logger.error(f"Local file not found for upload: {local_file_path}")
        raise
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error(f"AWS credentials not found or incomplete: {e}")
        raise
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        logger.error(f"S3 ClientError uploading {local_file_path}: {error_code} - {e}")
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error uploading {local_file_path} to S3: {e}", exc_info=True
        )
        raise
