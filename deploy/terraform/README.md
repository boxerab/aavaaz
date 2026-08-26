# Aavaaz — Terraform AWS Deployment

Single-click deployment of Aavaaz to AWS with GPU-accelerated ECS tasks.

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.5
- AWS CLI configured (`aws configure`)
- Docker (to build and push the image)

## Quick Start

```bash
# 1. Initialize Terraform
terraform init

# 2. Deploy infrastructure
terraform apply

# 3. Build and push the Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_url | cut -d/ -f1)
docker build -t aavaaz ../..
docker tag aavaaz:latest $(terraform output -raw ecr_repository_url):latest
docker push $(terraform output -raw ecr_repository_url):latest

# 4. Force ECS to pull the new image
aws ecs update-service --cluster aavaaz --service aavaaz --force-new-deployment
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `us-east-1` | AWS region |
| `model` | `large-v3` | Whisper model name |
| `instance_gpu` | `g5.xlarge` | GPU instance type |
| `desired_count` | `1` | Number of tasks |
| `api_key` | `""` | API key (empty = no auth) |
| `max_clients` | `100` | Concurrent WebSocket clients per task |
| `max_connection_time` | `900` | Seconds a client may stay connected |
| `loadgen_count` | `0` | Load generator instances for `loadtest/` |
| `loadgen_instance_type` | `c6i.4xlarge` | Load generator instance type |

Example with custom settings:
```bash
terraform apply \
  -var="aws_region=eu-west-1" \
  -var="model=large-v3" \
  -var="instance_gpu=g5.2xlarge" \
  -var="desired_count=2" \
  -var="api_key=my-secret-key"
```

## Architecture

```
Internet → ALB (ports 8000, 9090) → ECS Service → GPU EC2 Instances (g5.xlarge)
                                                    └─ Aavaaz container (NVIDIA GPU)
```

- **ECS on EC2** with GPU AMI (not Fargate — Fargate doesn't support GPUs)
- **ALB** terminates HTTP and WebSocket connections
- **Auto Scaling Group** manages GPU instances
- **ECR** stores the Aavaaz Docker image
- **CloudWatch** captures logs (14-day retention)

## Load test

`loadgen_count=1` covers about 2,500 streaming clients per instance. Each instance sets itself up from `loadtest/setup_loadgen.sh` on first boot (repo, venv, LibriSpeech tracks, file limits) and has no SSH key, so use SSM:

```bash
aws ssm start-session --target $(terraform output -json loadgen_instance_ids | jq -r '.[0]')
```

Task private IPs for `loadtest/scrape_metrics.py`:

```bash
aws ecs list-tasks --cluster aavaaz --service-name aavaaz --query 'taskArns' --output text \
  | xargs aws ecs describe-tasks --cluster aavaaz --tasks \
  --query 'tasks[].attachments[].details[?name==`privateIPv4Address`].value' --output text \
  | tr '\t' '\n' | sed 's/$/:9100/' | paste -sd,
```

## Teardown

```bash
terraform destroy
```
