# Global Tension Monitor — AWS ingestion setup

This is the first AWS step for the Render-based GTM app.

Goal:

```text
GDELT live data
  -> AWS Lambda collector
  -> S3 raw JSON archive
  -> DynamoDB normalized events
  -> Render app can later read from DynamoDB
```

## 1. Create S3 bucket

AWS Console -> S3 -> Create bucket

Suggested bucket name:

```text
gtm-raw-events-tomas
```

Recommended settings:

- Region: `eu-north-1` Stockholm
- Block all public access: enabled
- Versioning: disabled for MVP
- Default encryption: SSE-S3 enabled

## 2. Create DynamoDB table

AWS Console -> DynamoDB -> Tables -> Create table

```text
Table name: gtm_events
Partition key: pk  String
Sort key: sk       String
Table settings: On-demand
Region: eu-north-1 Stockholm
```

## 3. Create Lambda function

AWS Console -> Lambda -> Create function

```text
Function name: gtm-gdelt-collector
Runtime: Python 3.12
Architecture: x86_64
Region: eu-north-1 Stockholm
```

Paste the code from:

```text
aws/lambda_collector.py
```

Set Lambda environment variables:

```text
GTM_EVENTS_TABLE=gtm_events
GTM_RAW_BUCKET=gtm-raw-events-tomas
AWS_REGION=eu-north-1
```

Increase Lambda timeout:

```text
Timeout: 60 seconds
Memory: 256 MB
```

## 4. Lambda IAM permissions

Attach this inline policy to the Lambda execution role. Replace the account ID automatically by selecting the table/bucket in AWS policy editor if preferred.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:BatchWriteItem"],
      "Resource": "arn:aws:dynamodb:eu-north-1:*:table/gtm_events"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::gtm-raw-events-tomas/*"
    }
  ]
}
```

The default Lambda basic execution role should already contain CloudWatch Logs permissions.

## 5. Test Lambda

Lambda -> Test -> create test event:

```json
{}
```

Expected result:

```json
{
  "statusCode": 200,
  "source": "GDELT_DOC",
  "articles_received": 75,
  "items_written": 75
}
```

Then verify:

- S3 contains `source=gdelt_doc/.../batch-*.json.gz`
- DynamoDB table `gtm_events` contains items
- CloudWatch logs show the result JSON

## 6. Add EventBridge Scheduler

AWS Console -> EventBridge Scheduler -> Create schedule

```text
Name: gtm-gdelt-every-15-min
Schedule pattern: rate(15 minutes)
Target: AWS Lambda Invoke
Function: gtm-gdelt-collector
Payload: {}
Region: eu-north-1 Stockholm
```

For the first day, `rate(1 hour)` is also fine to reduce noise and cost.

## 7. Render environment variables later

After AWS data writes are verified, add these to Render:

```text
GTM_AWS_ENABLED=true
AWS_REGION=eu-north-1
GTM_EVENTS_TABLE=gtm_events
AWS_ACCESS_KEY_ID=<readonly-render-user-access-key>
AWS_SECRET_ACCESS_KEY=<readonly-render-user-secret>
```

Use a separate IAM user for Render with read-only DynamoDB access only.

## 8. Planned Render change

The current Render app keeps live data in memory. The next step is to import `aws/render_aws_events.py` in `app.py` and make `/api/events` or a new `/api/aws-events` read from DynamoDB.

Keep fallback behavior:

```text
DynamoDB available -> use AWS events
DynamoDB unavailable -> use existing in-memory cache/fallback events
```
