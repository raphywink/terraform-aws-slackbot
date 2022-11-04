#################
#   TERRAFORM   #
#################

terraform {
  required_version = "~> 1.0"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }

    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

###########
#   AWS   #
###########

provider "aws" {
  region = "us-east-1"
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

################
#   SLACKBOT   #
################

locals { fqdn = "slack.${var.domain}" }

module "slackbot" {
  providers                = { aws.us_east_1 = aws.us_east_1 }
  source                   = "./.."
  api_name                 = "slackbot"
  default_function_name    = "slackbot-default"
  distribution_aliases     = [local.fqdn]
  distribution_description = local.fqdn
  edge_function_name       = "slackbot-edge"
  event_bus_name           = "slackbot"
  secret_hash              = md5(aws_secretsmanager_secret_version.secret.secret_string)
  secret_name              = "slackbot"

  api_sync_handlers = {
    "ANY /health"     = aws_lambda_function.health.invoke_arn
    "POST /callbacks" = aws_lambda_function.callbacks.invoke_arn
    "POST /menus"     = aws_lambda_function.menus.invoke_arn
  }

  distribution_viewer_certificate = {
    acm_certificate_arn      = data.aws_acm_certificate.us_east_1.arn
    minimum_protocol_version = "TLSv1.2_2021"
    ssl_support_method       = "sni-only"
  }
}

output "healthcheck" { value = "https://${local.fqdn}/health" }

#######################
#   SLACKBOT ADDONS   #
#######################

data "archive_file" "health" {
  source_file = "${path.module}/functions/health/index.py"
  output_path = "${path.module}/functions/health/package.zip"
  type        = "zip"
}

resource "aws_iam_role" "health" {
  name = "slackbot-health"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  inline_policy {
    name = "access"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = "logs:*"
        Resource = "*"
      }]
    })
  }
}

resource "aws_lambda_function" "health" {
  provider         = aws.us_east_1
  architectures    = ["arm64"]
  description      = "slackbot health function"
  filename         = data.archive_file.health.output_path
  function_name    = "slackbot-health"
  handler          = "index.handler"
  memory_size      = 256
  role             = aws_iam_role.menus.arn
  runtime          = "python3.9"
  source_code_hash = data.archive_file.health.output_base64sha256
}

data "archive_file" "callbacks" {
  source_file = "${path.module}/functions/callbacks/index.py"
  output_path = "${path.module}/functions/callbacks/package.zip"
  type        = "zip"
}

resource "aws_iam_role" "callbacks" {
  name = "slackbot-callbacks"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  inline_policy {
    name = "access"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = "logs:*"
        Resource = "*"
      }]
    })
  }
}

resource "aws_lambda_function" "callbacks" {
  provider         = aws.us_east_1
  architectures    = ["arm64"]
  description      = "slackbot callbacks function"
  filename         = data.archive_file.callbacks.output_path
  function_name    = "slackbot-callbacks"
  handler          = "index.handler"
  memory_size      = 256
  role             = aws_iam_role.menus.arn
  runtime          = "python3.9"
  source_code_hash = data.archive_file.callbacks.output_base64sha256
}

data "archive_file" "menus" {
  source_file = "${path.module}/functions/menus/index.py"
  output_path = "${path.module}/functions/menus/package.zip"
  type        = "zip"
}

resource "aws_iam_role" "menus" {
  name = "slackbot-menus"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  inline_policy {
    name = "access"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Effect   = "Allow"
        Action   = "logs:*"
        Resource = "*"
      }]
    })
  }
}

resource "aws_lambda_function" "menus" {
  provider         = aws.us_east_1
  architectures    = ["arm64"]
  description      = "slackbot menus function"
  filename         = data.archive_file.menus.output_path
  function_name    = "slackbot-menus"
  handler          = "index.handler"
  memory_size      = 256
  role             = aws_iam_role.menus.arn
  runtime          = "python3.9"
  source_code_hash = data.archive_file.menus.output_base64sha256
}

###########
#   DNS   #
###########

variable "domain" { type = string }

data "aws_acm_certificate" "us_east_1" {
  provider = aws.us_east_1
  domain   = var.domain
  types    = ["AMAZON_ISSUED"]
}

data "aws_route53_zone" "zone" {
  name = "${var.domain}."
}

resource "aws_route53_record" "aliases" {
  for_each = toset([local.fqdn])
  name     = each.value
  type     = "A"
  zone_id  = data.aws_route53_zone.zone.zone_id

  alias {
    zone_id                = module.slackbot.distribution.hosted_zone_id
    name                   = module.slackbot.distribution.domain_name
    evaluate_target_health = false
  }
}

##############
#   SECRET   #
##############

variable "secret" {
  type = object({
    SLACK_OAUTH_CLIENT_ID     = string
    SLACK_OAUTH_CLIENT_SECRET = string
    SLACK_OAUTH_SCOPE         = string
    SLACK_OAUTH_USER_SCOPE    = string
    SLACK_OAUTH_ERROR_URI     = string
    SLACK_OAUTH_REDIRECT_URI  = string
    SLACK_OAUTH_SUCCESS_URI   = string
    SLACK_SIGNING_SECRET      = string
    SLACK_SIGNING_VERSION     = string
  })
}

resource "aws_secretsmanager_secret_version" "secret" {
  provider      = aws.us_east_1
  secret_id     = module.slackbot.secret.id
  secret_string = jsonencode(var.secret)
}
