# Staging deployment

All AWS calls below run inside the managed AWS MCP Server's `aws___run_script`
with boto3, under `DextoDemoRole`, in `us-east-1`. The deployer's computer has no
AWS credentials, AWS CLI, or kubectl. CodeBuild's build container uses its own
service role and AWS CLI for the ECR login in `buildspec.yml`; those commands are
not deployer commands. Account IDs are always resolved with STS at deployment time.
Infrastructure (buckets, ECR repositories, roles, project source configuration,
networking, and log groups) is provisioned by `brahma-dexto-demo/demo-infra`.
CodeBuild sources must point to the published repository and accept the supplied
commit SHA; these local repositories have not been pushed.

1. Commit the change and obtain its SHA. Use `aws___run_script` to start
   `accounts-api-image` at that revision and wait for success. Buildspec only builds
   and pushes; it does not deploy.

```python
import boto3
import time

session = boto3.Session(region_name="us-east-1")
account = session.client("sts").get_caller_identity()["Account"]
sha = "<sha>"  # Full committed source revision
codebuild = session.client("codebuild")
build_id = codebuild.start_build(
    projectName="accounts-api-image",
    sourceVersion=sha,
    environmentVariablesOverride=[
        {
            "name": "ECR_URI",
            "value": f"{account}.dkr.ecr.us-east-1.amazonaws.com/brahma-demo/accounts-api",
            "type": "PLAINTEXT",
        }
    ],
)["build"]["id"]
# For long builds, return build_id and poll in subsequent run_script calls.
for _ in range(60):
    build = codebuild.batch_get_builds(ids=[build_id])["builds"][0]
    status = build["buildStatus"]
    if status == "SUCCEEDED":
        break
    if status in {"FAILED", "FAULT", "STOPPED", "TIMED_OUT"}:
        raise RuntimeError(f"Build {build_id}: {status}; inspect build['logs']")
    time.sleep(10)
else:
    raise TimeoutError(f"Build {build_id} is still running; resume polling")
image = f"{account}.dkr.ecr.us-east-1.amazonaws.com/brahma-demo/accounts-api:{sha}"
print({"image": image, "account": account})
```

2. Confirm the synthetic input is available at
   `s3://brahma-demo-data-<account>/accounts/accounts.json`. For a fresh demo,
   read the complete `data/accounts/accounts.json` on the computer (about 52 KB)
   and embed its JSON text directly in an `aws___run_script` Python string.
   Replace the placeholder below with the **entire file contents**, preserving
   all 200 accounts. The MCP sandbox cannot read the computer's file path.

```python
import boto3
import json

session = boto3.Session(region_name="us-east-1")
account = session.client("sts").get_caller_identity()["Account"]
bucket = f"brahma-demo-data-{account}"
key = "accounts/accounts.json"
seed_json = r'''<paste the entire data/accounts/accounts.json JSON here>'''
json.loads(seed_json)  # Validate the embedded JSON before writing
body = seed_json.encode("utf-8")
s3 = session.client("s3")
s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
head = s3.head_object(Bucket=bucket, Key=key)
assert head["ContentLength"] == len(body), "Seed size mismatch"
assert head["ContentType"] == "application/json", "Seed content type mismatch"
print({"bucket": bucket, "key": key, "bytes": head["ContentLength"],
       "etag": head["ETag"]})
```

   Run this only through managed MCP. The bootstrap role grants `s3:PutObject`
   on this data bucket's `accounts/*` prefix under the normal MCP routing rules;
   CodeBuild's separate service role publishes the console JAR.

3. Render `k8s/deployment.yaml`: replace `ACCOUNTS_API_IMAGE` with the returned
   image and `ACCOUNT_ID` with the STS account. Namespace `demo` must already exist.
   Use the managed Amazon EKS MCP Server `apply_yaml` against cluster `brahma-demo`
   to apply `serviceaccount.yaml`, the rendered deployment, and `service.yaml`.
   Pod Identity for service account `accounts-api` must grant input-bucket read.
   For every image change, render the deployment again with the new SHA image
   and re-apply it using `apply_yaml`.
4. Poll `read_k8s_resource` for the Deployment in namespace
   `demo`. Require `status.observedGeneration >= metadata.generation`,
   `status.updatedReplicas == 2`, and `status.availableReplicas == 2` before
   considering rollout complete. Use `list_k8s_resources`, `get_pod_logs`, and
   `get_k8s_events` if readiness fails; `/healthz` checks process health, not S3
   connectivity.
5. Read Service `accounts-api` in namespace `demo`. Obtain
   `status.loadBalancer.ingress[0].hostname` after it is assigned. Service port 80
   forwards to container port 8000. Validate the data path using the live contract:

```sh
uv sync --locked
BASE_URL=http://<load-balancer-hostname> uv run pytest tests/contract
```

Record that URL for the CloudFormation `AccountsApiUrl` parameter update in
`ops-console/DEPLOY.md`; the stack sets `ACCOUNTS_API_URL`.

## Local run

```sh
docker build -t accounts-api:local .
docker run --rm -p 8000:8000 accounts-api:local
```

The container uses its bundled dataset by default. To substitute local data:

```sh
docker run --rm -p 8000:8000 -e LOCAL_DATA_DIR=/data -v "$PWD/data:/data:ro" accounts-api:local
```
