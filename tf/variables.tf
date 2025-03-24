variable "project_name" {
  type        = string
  description = "Name of the project for this application."
}

variable "region" {
  type        = string
  description = "AWS region to deploy the application in."
}

variable "runtime" {
  type        = string
  description = "The runtime for the Lambda function."
}

variable "sns_topic_name" {
  type        = string
  description = "Name of the SNS topic to send notifications to."
}

variable "app_creds" {
  type        = map(any)
  description = "The parameters to store in Parameter Store."
  default = {
    "intervals/api_key" = {}
    "intervals/uid"     = {}
  }
}

variable "export_cron" {
  type        = string
  description = "The cron expression to run the export function."
}
# Example input
# export_cron           = "cron(0 1 ? * * *)"

variable "weekly_cron" {
  type        = string
  description = "The cron expression to run functions on a weekly frequency."
}
# Example input
# weekly_cron           = "cron(0 9 ? * 2 *)"

variable "monthly_cron" {
  type        = string
  description = "The cron expression to run functions on a monthly frequency."
}
# Example input
# monthly_cron          = "cron(0 10 1 * ? *)"


variable "notifications_enabled" {
  type        = string
  description = "Set to true or false to toggle notifications being sent"
}