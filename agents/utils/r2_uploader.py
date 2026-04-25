#!/usr/bin/env python3
"""Fallback R2 uploader using boto3 S3-compatible API. Used when wrangler CLI is unavailable."""
import argparse
import os
import sys

def upload(file_path: str, key: str, content_type: str, bucket: str | None = None) -> str:
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        print("boto3 not installed. Run: pip install boto3", file=sys.stderr)
        sys.exit(1)

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    access_key = os.environ.get("CF_R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("CF_R2_SECRET_ACCESS_KEY")
    bucket_name = bucket or os.environ.get("CF_R2_BUCKET", "iim-media")
    public_url = os.environ.get("CF_R2_PUBLIC_URL", "https://media.internetinmyanmar.com")

    if not all([account_id, access_key, secret_key]):
        print("Missing env vars: CLOUDFLARE_ACCOUNT_ID, CF_R2_ACCESS_KEY_ID, CF_R2_SECRET_ACCESS_KEY", file=sys.stderr)
        sys.exit(1)

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    with open(file_path, "rb") as f:
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=f,
            ContentType=content_type,
        )

    public = f"{public_url}/{key}"
    print(public)
    return public


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a file to Cloudflare R2")
    parser.add_argument("--file", required=True, help="Local file path to upload")
    parser.add_argument("--key", required=True, help="R2 object key (path within bucket)")
    parser.add_argument("--content-type", default="image/jpeg", help="MIME type")
    parser.add_argument("--bucket", help="R2 bucket name (overrides CF_R2_BUCKET env var)")
    args = parser.parse_args()
    upload(args.file, args.key, args.content_type, args.bucket)
