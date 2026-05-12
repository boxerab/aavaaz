# Aavaaz — Single-click AWS deploy (ECS Fargate with GPU)
#
# Usage:
#   cd deploy/terraform
#   terraform init
#   terraform apply
#
# This provisions:
#   - VPC with public subnets
#   - ECS cluster with GPU-enabled Fargate tasks
#   - Application Load Balancer (ports 8000 REST, 9090 WebSocket)
#   - ECR repository for the Aavaaz Docker image
#   - CloudWatch log group

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------- Variables ----------

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "model" {
  description = "Whisper model name"
  type        = string
  default     = "large-v3"
}

variable "instance_gpu" {
  description = "GPU instance type for ECS tasks"
  type        = string
  default     = "g5.xlarge"
}

variable "desired_count" {
  description = "Number of ECS tasks"
  type        = number
  default     = 1
}

variable "api_key" {
  description = "Optional API key for authentication (leave empty to disable)"
  type        = string
  default     = ""
  sensitive   = true
}

# ---------- Networking ----------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "aavaaz-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnets = ["10.0.10.0/24", "10.0.11.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
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

# ---------- ECS Cluster ----------

resource "aws_ecs_cluster" "aavaaz" {
  name = "aavaaz"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ---------- IAM ----------

resource "aws_iam_role" "ecs_task_execution" {
  name = "aavaaz-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "aavaaz-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# ---------- CloudWatch ----------

resource "aws_cloudwatch_log_group" "aavaaz" {
  name              = "/ecs/aavaaz"
  retention_in_days = 14
}

# ---------- Security Groups ----------

resource "aws_security_group" "alb" {
  name_prefix = "aavaaz-alb-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "aavaaz-ecs-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- ALB ----------

resource "aws_lb" "aavaaz" {
  name               = "aavaaz-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets
}

resource "aws_lb_target_group" "rest" {
  name        = "aavaaz-rest"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_lb_target_group" "ws" {
  name        = "aavaaz-ws"
  port        = 9090
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {
    path                = "/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    matcher             = "200-499"
  }
}

resource "aws_lb_listener" "rest" {
  load_balancer_arn = aws_lb.aavaaz.arn
  port              = 8000
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.rest.arn
  }
}

resource "aws_lb_listener" "ws" {
  load_balancer_arn = aws_lb.aavaaz.arn
  port              = 9090
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ws.arn
  }
}

# ---------- ECS Task Definition ----------

resource "aws_ecs_task_definition" "aavaaz" {
  family                   = "aavaaz"
  requires_compatibilities = ["EC2"]
  network_mode             = "awsvpc"
  cpu                      = "4096"
  memory                   = "16384"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "aavaaz"
    image = "${aws_ecr_repository.aavaaz.repository_url}:latest"

    essential = true

    portMappings = [
      { containerPort = 8000, protocol = "tcp" },
      { containerPort = 9090, protocol = "tcp" },
    ]

    command = compact([
      "--model", var.model,
      var.api_key != "" ? "--api-key" : "",
      var.api_key != "" ? var.api_key : "",
    ])

    resourceRequirements = [{
      type  = "GPU"
      value = "1"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.aavaaz.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "aavaaz"
      }
    }
  }])
}

# ---------- ECS Service ----------

resource "aws_ecs_capacity_provider" "gpu" {
  name = "aavaaz-gpu"

  auto_scaling_group_provider {
    auto_scaling_group_arn         = aws_autoscaling_group.gpu.arn
    managed_termination_protection = "DISABLED"

    managed_scaling {
      status          = "ENABLED"
      target_capacity = 100
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "aavaaz" {
  cluster_name       = aws_ecs_cluster.aavaaz.name
  capacity_providers = [aws_ecs_capacity_provider.gpu.name]
}

resource "aws_ecs_service" "aavaaz" {
  name            = "aavaaz"
  cluster         = aws_ecs_cluster.aavaaz.id
  task_definition = aws_ecs_task_definition.aavaaz.arn
  desired_count   = var.desired_count

  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.gpu.name
    weight            = 1
  }

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.rest.arn
    container_name   = "aavaaz"
    container_port   = 8000
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.ws.arn
    container_name   = "aavaaz"
    container_port   = 9090
  }
}

# ---------- GPU Auto Scaling Group ----------

data "aws_ami" "ecs_gpu" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-ecs-gpu-hvm-*-x86_64-ebs"]
  }
}

resource "aws_launch_template" "gpu" {
  name_prefix   = "aavaaz-gpu-"
  image_id      = data.aws_ami.ecs_gpu.id
  instance_type = var.instance_gpu

  iam_instance_profile {
    arn = aws_iam_instance_profile.ecs_instance.arn
  }

  user_data = base64encode(<<-EOF
    #!/bin/bash
    echo ECS_CLUSTER=${aws_ecs_cluster.aavaaz.name} >> /etc/ecs/ecs.config
    echo ECS_ENABLE_GPU_SUPPORT=true >> /etc/ecs/ecs.config
  EOF
  )

  network_interfaces {
    security_groups = [aws_security_group.ecs.id]
  }
}

resource "aws_autoscaling_group" "gpu" {
  name_prefix      = "aavaaz-gpu-"
  desired_capacity = var.desired_count
  max_size         = var.desired_count * 2
  min_size         = 0
  vpc_zone_identifier = module.vpc.private_subnets

  launch_template {
    id      = aws_launch_template.gpu.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }
}

resource "aws_iam_role" "ecs_instance" {
  name = "aavaaz-ecs-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_instance" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "ecs_instance" {
  name = "aavaaz-ecs-instance"
  role = aws_iam_role.ecs_instance.name
}

# ---------- Outputs ----------

output "rest_endpoint" {
  description = "REST API endpoint"
  value       = "http://${aws_lb.aavaaz.dns_name}:8000"
}

output "websocket_endpoint" {
  description = "WebSocket endpoint"
  value       = "ws://${aws_lb.aavaaz.dns_name}:9090"
}

output "ecr_repository_url" {
  description = "ECR repository URL — push your image here"
  value       = aws_ecr_repository.aavaaz.repository_url
}
