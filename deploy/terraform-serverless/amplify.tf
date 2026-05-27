# Aavaaz Dashboard — AWS Amplify Hosting
#
# Deploys the Next.js dashboard to AWS Amplify.
# No Vercel account needed — runs entirely on your AWS credits.

resource "aws_amplify_app" "dashboard" {
  name       = "aavaaz-dashboard-${var.environment}"
  repository = var.github_repo_url

  build_spec = <<-EOT
    version: 1
    frontend:
      phases:
        preBuild:
          commands:
            - cd dashboard
            - npm ci
        build:
          commands:
            - npm run build
      artifacts:
        baseDirectory: dashboard/.next
        files:
          - '**/*'
      cache:
        paths:
          - dashboard/node_modules/**/*
          - dashboard/.next/cache/**/*
  EOT

  environment_variables = {
    NEXT_PUBLIC_COGNITO_USER_POOL_ID = aws_cognito_user_pool.aavaaz.id
    NEXT_PUBLIC_COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.dashboard.id
    NEXT_PUBLIC_API_URL              = aws_apigatewayv2_api.saas.api_endpoint
    NEXT_PUBLIC_WS_URL              = var.modal_ws_url
  }

  custom_rule {
    source = "/<*>"
    status = "404-200"
    target = "/index.html"
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.dashboard.id
  branch_name = "main"

  framework = "Next.js - SSR"

  environment_variables = {
    NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY = var.stripe_publishable_key
  }
}

resource "aws_amplify_domain_association" "dashboard" {
  app_id      = aws_amplify_app.dashboard.id
  domain_name = "app.${var.domain}"

  sub_domain {
    branch_name = aws_amplify_branch.main.branch_name
    prefix      = ""
  }
}
