###########
#   API   #
###########

variable "api_description" {
  type        = string
  description = "Slack API description"
  default     = "Slack API"
}

variable "api_name" {
  type        = string
  description = "Slack API name"
}

variable "api_integration_description" {
  type        = string
  description = "Slack API default integration description"
  default     = "Slack API default integration"
}

variable "api_stage_description" {
  type        = string
  description = "Slack API default stage description"
  default     = "Slack API default stage"
}

variable "api_sync_handlers" {
  type        = map(string)
  description = "Optional route key => Lambda invocation ARN mappings"
  default     = {}
}

######################
#   DEFAULT LAMBDA   #
######################

variable "default_function_description" {
  type        = string
  description = "Default Slack handler function description"
  default     = "Default Slack handler"
}

variable "default_function_logs_retention_in_days" {
  type        = number
  description = "Default Slack handler function log retention in days"
  default     = 14
}

variable "default_function_name" {
  type        = string
  description = "Default Slack handler function name"
}

###################
#   EDGE LAMBDA   #
###################

variable "edge_function_description" {
  type        = string
  description = "CloudFront@Edge Slack handler function description"
  default     = "CloudFront@Edge Slack handler"
}

variable "edge_function_name" {
  type        = string
  description = "CloudFront@Edge Slack handler function name"
}

variable "event_bus_name" {
  type        = string
  description = "EventBridge bus name"
}

##################
#   CLOUDFRONT   #
##################

variable "distribution_aliases" {
  type        = list(string)
  description = "CloudFront distribution aliases"
  default     = []
}

variable "distribution_description" {
  type        = string
  description = "CloudFront distribution description"
  default     = "Slackbot API"
}

variable "distribution_enabled" {
  type        = bool
  description = "CloudFront distribution enabled switch"
  default     = true
}

variable "distribution_http_version" {
  type        = string
  description = "CloudFront distribution HTTP version option"
  default     = "http2and3"
}

variable "distribution_is_ipv6_enabled" {
  type        = bool
  description = "CloudFront distribution IPv6 switch"
  default     = true
}

variable "distribution_logging_configurations" {
  type = list(object({
    bucket          = optional(string)
    prefix          = optional(string)
    include_cookies = optional(bool)
  }))
  description = "CloudFront distribution logging configurations"
  default     = []
}

variable "distribution_price_class" {
  type        = string
  description = "CloudFront distribution price class"
  default     = "PriceClass_All"
}

variable "distribution_viewer_certificate" {
  type = object({
    acm_certificate_arn            = optional(string)
    cloudfront_default_certificate = optional(bool)
    iam_certificate_id             = optional(string)
    minimum_protocol_version       = optional(string)
    ssl_support_method             = optional(string)
  })
  description = "CloudFront distribution viewer certificate configuration"
  default     = { cloudfront_default_certificate = true }
}

############
#   LOGS   #
############

variable "log_retention_in_days" {
  type        = number
  description = "Slack API log retention in days"
  default     = 14
}

##############
#   SECRET   #
##############

variable "secret_hash" {
  type        = string
  description = "SecretsManager secret hash (to trigger redeployment)"
  default     = ""
}

variable "secret_name" {
  type        = string
  description = "SecretsManager secret name"
}
