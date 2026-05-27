# Aavaaz SaaS — EKS with Karpenter for GPU Auto-Scaling
#
# This provisions:
#   - EKS cluster with managed node group (system workloads)
#   - Karpenter for GPU node provisioning (scale to zero)
#   - ALB Ingress Controller
#   - VPC with public/private subnets
#   - ECR repository
#   - RDS PostgreSQL (user data, usage tracking)
#   - ElastiCache Redis (rate limiting, sessions)
#   - S3 bucket (audio files, transcripts)
#   - Cognito User Pool (authentication)
#
# Usage:
#   cd deploy/terraform-saas
#   terraform init
#   terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }
}

provider "aws" {
  region = var.region
}

# ---------- Variables ----------

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "aavaaz-saas"
}

variable "domain" {
  description = "Domain name for the SaaS platform"
  type        = string
  default     = "aavaaz.dev"
}

variable "db_password" {
  description = "PostgreSQL master password"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

# ---------- Networking ----------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnets = ["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/role/elb"                    = 1
    "kubernetes.io/cluster/${var.cluster_name}" = "owned"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"           = 1
    "kubernetes.io/cluster/${var.cluster_name}" = "owned"
    "karpenter.sh/discovery"                    = var.cluster_name
  }
}

# ---------- EKS Cluster ----------

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.29"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    system = {
      instance_types = ["m5.large"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2

      labels = {
        workload = "system"
      }
    }
  }

  # Enable OIDC for Karpenter and other IAM roles
  enable_irsa = true

  tags = {
    "karpenter.sh/discovery" = var.cluster_name
    Environment              = var.environment
  }
}

# ---------- Karpenter (GPU Auto-Scaling) ----------

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.0"

  cluster_name = module.eks.cluster_name

  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["karpenter:karpenter"]

  # Create instance profile for nodes Karpenter launches
  create_instance_profile = true
}

# ---------- ECR ----------

resource "aws_ecr_repository" "aavaaz" {
  name                 = "aavaaz"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "dashboard" {
  name                 = "aavaaz-dashboard"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# ---------- RDS PostgreSQL ----------

resource "aws_db_subnet_group" "aavaaz" {
  name       = "${var.cluster_name}-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.cluster_name}-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_db_instance" "aavaaz" {
  identifier           = "${var.cluster_name}-db"
  engine               = "postgres"
  engine_version       = "16.1"
  instance_class       = "db.t4g.medium"
  allocated_storage    = 50
  max_allocated_storage = 200

  db_name  = "aavaaz"
  username = "aavaaz"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.aavaaz.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 7
  multi_az               = var.environment == "prod"
  deletion_protection    = var.environment == "prod"
  skip_final_snapshot    = var.environment != "prod"

  tags = { Environment = var.environment }
}

# ---------- ElastiCache Redis ----------

resource "aws_elasticache_subnet_group" "aavaaz" {
  name       = "${var.cluster_name}-redis"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis" {
  name_prefix = "${var.cluster_name}-redis-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_elasticache_replication_group" "aavaaz" {
  replication_group_id = "${var.cluster_name}-redis"
  description          = "Aavaaz SaaS Redis cluster"
  node_type            = "cache.t4g.medium"
  num_cache_clusters   = var.environment == "prod" ? 2 : 1

  subnet_group_name  = aws_elasticache_subnet_group.aavaaz.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = { Environment = var.environment }
}

# ---------- S3 Bucket (Audio & Transcripts) ----------

resource "aws_s3_bucket" "data" {
  bucket = "${var.cluster_name}-data-${var.region}"

  tags = { Environment = var.environment }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "archive-old-transcripts"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

# ---------- Cognito User Pool ----------

resource "aws_cognito_user_pool" "aavaaz" {
  name = "${var.cluster_name}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_uppercase = true
    require_symbols   = false
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = { Environment = var.environment }
}

resource "aws_cognito_user_pool_client" "dashboard" {
  name         = "${var.cluster_name}-dashboard"
  user_pool_id = aws_cognito_user_pool.aavaaz.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  supported_identity_providers = ["COGNITO"]

  callback_urls = [
    "https://app.${var.domain}/",
    "http://localhost:3000/",
  ]
  logout_urls = [
    "https://app.${var.domain}/",
    "http://localhost:3000/",
  ]
}

# ---------- Outputs ----------

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  value = aws_ecr_repository.aavaaz.repository_url
}

output "dashboard_ecr_url" {
  value = aws_ecr_repository.dashboard.repository_url
}

output "database_endpoint" {
  value = aws_db_instance.aavaaz.endpoint
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.aavaaz.primary_endpoint_address
}

output "s3_bucket" {
  value = aws_s3_bucket.data.id
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.aavaaz.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.dashboard.id
}

output "karpenter_instance_profile_name" {
  value = module.karpenter.instance_profile_name
}
