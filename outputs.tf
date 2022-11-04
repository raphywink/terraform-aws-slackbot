output "api" {
  description = "API Gateway API"
  value       = aws_apigatewayv2_api.api
}

output "distribution" {
  description = "CloudFront distribution"
  value       = aws_cloudfront_distribution.distribution
}

output "secret" {
  description = "SecretsManager secret container"
  value       = aws_secretsmanager_secret.secret
}
