# Eventbridge rule to run the export function at the frequency defined by the export_cron variable.
resource "aws_cloudwatch_event_rule" "export" {
  name        = "${var.project_name}_export"
  description = "Rule to invoke ${var.project_name}_export function"

  schedule_expression = var.export_cron
}

resource "aws_cloudwatch_event_target" "export" {
  rule      = aws_cloudwatch_event_rule.export.name
  target_id = "export"
  arn       = aws_lambda_function.export.arn
}

# Eventbridge rule to run the notify function weekly as defined by the weekly_cron variable.
resource "aws_cloudwatch_event_rule" "notify_weekly" {
  name        = "${var.project_name}_notify_weekly"
  description = "Rule to invoke the ${var.project_name}_notify function on a weekly basis"

  schedule_expression = var.weekly_cron
}

resource "aws_cloudwatch_event_target" "nutrition_weekly" {
  rule      = aws_cloudwatch_event_rule.nutrition_weekly.name
  target_id = "nutrition_weekly"
  arn       = aws_lambda_function.nutrition.arn
}

# Eventbridge rule to run the nutrition function weekly as defined by the weekly_cron variable.
resource "aws_cloudwatch_event_rule" "nutrition_weekly" {
  name        = "${var.project_name}_nutrition_weekly"
  description = "Rule to invoke the ${var.project_name}_nutrition function on a weekly basis"

  schedule_expression = var.weekly_cron
}

resource "aws_cloudwatch_event_target" "notify_weekly" {
  rule      = aws_cloudwatch_event_rule.notify_weekly.name
  target_id = "notify_weekly"
  arn       = aws_lambda_function.notify.arn
}

# Eventbridge rule to run the nutrition function monthly as defined by the monthly_cron variable.
resource "aws_cloudwatch_event_rule" "notify_monthly" {
  name        = "${var.project_name}_notify_monthly"
  description = "Rule to invoke the ${var.project_name}_notify function on a monthly basis"

  schedule_expression = var.monthly_cron
}

resource "aws_cloudwatch_event_target" "notify_monthly" {
  rule      = aws_cloudwatch_event_rule.notify_monthly.name
  target_id = "notify_monthly"
  arn       = aws_lambda_function.notify.arn
}