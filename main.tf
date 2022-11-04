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
      source                = "hashicorp/aws"
      version               = "~> 4.0"
      configuration_aliases = [aws.us_east_1]
    }

    local = {
      source  = "hashicorp/local"
      version = "~> 2.2"
    }
  }
}

############
#   DATA   #
############

data "aws_region" "current" {}

#######################
#   SECRET CONTAINER  #
#######################

resource "aws_secretsmanager_secret" "secret" {
  provider = aws.us_east_1
  name     = var.secret_name
}

#######################
#   EVENTBRIDGE BUS   #
#######################

resource "aws_cloudwatch_event_bus" "bus" {
  name = var.event_bus_name
}

########################
#   DEFAULT FUNCTION   #
########################

data "archive_file" "default" {
  source_dir  = "${path.module}/functions/default/src"
  output_path = "${path.module}/functions/default/package.zip"
  type        = "zip"
}

resource "aws_iam_role" "default" {
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AssumeLambdaEdge"
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
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = "logs:*"
        Resource = "*"
      }]
    })
  }
}

resource "aws_lambda_function" "default" {
  architectures    = ["arm64"]
  description      = var.default_function_description
  filename         = data.archive_file.default.output_path
  function_name    = var.default_function_name
  handler          = "index.handler"
  role             = aws_iam_role.default.arn
  runtime          = "python3.9"
  source_code_hash = data.archive_file.default.output_base64sha256
}

resource "aws_lambda_permission" "default" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.default.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/${aws_apigatewayv2_stage.default.name}/ANY/{default}"
}

resource "aws_cloudwatch_log_group" "default" {
  name              = "/aws/lambda/${aws_lambda_function.default.function_name}"
  retention_in_days = 14
}

#####################
#   EDGE FUNCTION   #
#####################

resource "local_file" "env" {
  filename        = "${path.module}/functions/edge/src/env.py"
  file_permission = "0644"

  content = templatefile("${path.module}/functions/edge/src/env.py.tpl", {
    ApiRegion      = data.aws_region.current.name
    EventBusName   = aws_cloudwatch_event_bus.bus.name
    EventBusRegion = data.aws_region.current.name
    SecretHash     = var.secret_hash
    SecretId       = aws_secretsmanager_secret.secret.id
    SecretRegion   = "us-east-1"
  })
}

data "archive_file" "edge" {
  depends_on  = [local_file.env]
  source_dir  = "${path.module}/functions/edge/src"
  output_path = "${path.module}/functions/edge/package.zip"
  type        = "zip"
}

resource "aws_iam_role" "edge" {
  name = var.edge_function_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AssumeLambdaEdge"
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = ["lambda.amazonaws.com", "edgelambda.amazonaws.com"] }
    }]
  })

  inline_policy {
    name = "access"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ExecuteApi"
          Effect   = "Allow"
          Action   = "execute-api:Invoke"
          Resource = "${aws_apigatewayv2_api.api.execution_arn}/*/*/*"
        },
        {
          Sid      = "EventBridge"
          Effect   = "Allow"
          Action   = "events:PutEvents"
          Resource = aws_cloudwatch_event_bus.bus.arn
        },
        {
          Sid      = "Logs"
          Effect   = "Allow"
          Action   = "logs:*"
          Resource = "*"
        },
        {
          Sid      = "SecretsManager"
          Effect   = "Allow"
          Action   = "secretsmanager:GetSecretValue"
          Resource = aws_secretsmanager_secret.secret.arn
        }
      ]
    })
  }
}

resource "aws_lambda_function" "edge" {
  provider         = aws.us_east_1
  architectures    = ["x86_64"]
  description      = var.edge_function_description
  filename         = data.archive_file.edge.output_path
  function_name    = var.edge_function_name
  handler          = "index.handler"
  memory_size      = 512
  publish          = true
  role             = aws_iam_role.edge.arn
  runtime          = "python3.9"
  source_code_hash = data.archive_file.edge.output_base64sha256
}

################
#   HTTP API   #
################

resource "aws_apigatewayv2_api" "api" {
  description   = var.api_description
  name          = var.api_name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  auto_deploy = true
  description = var.api_description
  name        = "$default"

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn

    format = jsonencode({
      httpMethod              = "$context.httpMethod"
      integrationErrorMessage = "$context.integrationErrorMessage"
      ip                      = "$context.identity.sourceIp"
      path                    = "$context.path"
      protocol                = "$context.protocol"
      requestId               = "$context.requestId"
      requestTime             = "$context.requestTime"
      responseLength          = "$context.responseLength"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
    })
  }

  lifecycle { ignore_changes = [deployment_id] }
}

resource "aws_apigatewayv2_route" "default" {
  api_id             = aws_apigatewayv2_api.api.id
  authorization_type = "AWS_IAM"
  route_key          = "ANY /{default}"
  target             = "integrations/${aws_apigatewayv2_integration.default.id}"
}

resource "aws_apigatewayv2_integration" "default" {
  api_id                 = aws_apigatewayv2_api.api.id
  description            = var.api_description
  integration_method     = "POST"
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.default.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigatewayv2/${aws_apigatewayv2_api.api.name}"
  retention_in_days = var.log_retention_in_days
}

#######################
#   HTTP API ADDONS   #
#######################

resource "aws_apigatewayv2_route" "sync" {
  for_each           = var.api_sync_handlers
  api_id             = aws_apigatewayv2_api.api.id
  authorization_type = "AWS_IAM"
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.sync[each.key].id}"
}

resource "aws_apigatewayv2_integration" "sync" {
  for_each               = var.api_sync_handlers
  api_id                 = aws_apigatewayv2_api.api.id
  description            = "${each.key} handler"
  integration_method     = "POST"
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value
  payload_format_version = "2.0"
}

resource "aws_lambda_permission" "sync" {
  for_each      = var.api_sync_handlers
  action        = "lambda:InvokeFunction"
  function_name = split("/", each.value)[3]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/${aws_apigatewayv2_stage.default.name}/${replace(each.key, " ", "")}"
}

resource "aws_cloudwatch_log_group" "sync" {
  for_each          = var.api_sync_handlers
  name              = "/aws/lambda/${split(":", split("/", each.value)[3])[6]}"
  retention_in_days = var.log_retention_in_days
}

##################
#   CLOUDFRONT   #
##################

resource "aws_cloudfront_distribution" "distribution" {
  aliases         = var.distribution_aliases
  comment         = var.distribution_description
  enabled         = var.distribution_enabled
  http_version    = var.distribution_http_version
  is_ipv6_enabled = var.distribution_is_ipv6_enabled
  price_class     = var.distribution_price_class

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    default_ttl            = 0
    max_ttl                = 0
    min_ttl                = 0
    target_origin_id       = "api"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = true
      headers      = ["x-slack-request-timestamp", "x-slack-signature"]

      cookies { forward = "none" }
    }

    lambda_function_association {
      event_type   = "origin-request"
      include_body = true
      lambda_arn   = aws_lambda_function.edge.qualified_arn
    }
  }

  dynamic "logging_config" {
    for_each = var.distribution_logging_configurations

    content {
      bucket          = logging_config.value.bucket
      prefix          = logging_config.value.prefix
      include_cookies = logging_config.value.include_cookies
    }
  }

  origin {
    domain_name = split("/", aws_apigatewayv2_api.api.api_endpoint)[2]
    origin_id   = "api"

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_keepalive_timeout = 5
      origin_protocol_policy   = "https-only"
      origin_read_timeout      = 30
      origin_ssl_protocols     = ["TLSv1.2"]
    }
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn            = var.distribution_viewer_certificate.acm_certificate_arn
    cloudfront_default_certificate = var.distribution_viewer_certificate.cloudfront_default_certificate
    iam_certificate_id             = var.distribution_viewer_certificate.iam_certificate_id
    minimum_protocol_version       = var.distribution_viewer_certificate.minimum_protocol_version
    ssl_support_method             = var.distribution_viewer_certificate.ssl_support_method
  }
}
