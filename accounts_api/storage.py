"""JSON storage using the shared local directory or S3 layout."""

import json
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


class JsonStore:
    def __init__(self):
        self.bucket = os.getenv("DATA_BUCKET")
        self.local_dir = Path(os.getenv("LOCAL_DATA_DIR", "./data"))
        self.s3 = boto3.client("s3") if self.bucket else None

    def read(self, key: str):
        if self.s3:
            body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        else:
            body = (self.local_dir / key).read_text()
        return json.loads(body)

    def read_optional(self, key: str):
        """Return None only when an optional object is absent."""
        try:
            return self.read(key)
        except FileNotFoundError:
            if self.s3:
                raise
            return None
        except ClientError as exc:
            if self.s3 and exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
                return None
            raise

    def write(self, key: str, value):
        body = json.dumps(value, indent=2) + "\n"
        if self.s3:
            self.s3.put_object(
                Bucket=self.bucket, Key=key, Body=body.encode(), ContentType="application/json"
            )
        else:
            path = self.local_dir / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
