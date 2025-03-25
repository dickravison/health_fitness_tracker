#Export
resource "aws_lambda_function" "export" {
  filename         = "../src/export.zip"
  function_name    = "${var.project_name}_export"
  role             = aws_iam_role.export.arn
  handler          = "main.main"
  source_code_hash = data.archive_file.export.output_base64sha256
  runtime          = var.runtime
  layers           = [data.aws_lambda_layer_version.requests.arn, "arn:aws:lambda:eu-west-1:015030872274:layer:AWS-Parameters-and-Secrets-Lambda-Extension-Arm64:11"]
  architectures    = ["arm64"]
  timeout          = "60"
  memory_size      = "128"

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.data.id
      PROJECT_NAME   = var.project_name
    }
  }

}

resource "aws_lambda_permission" "allow_eventbridge_pull_data" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.export.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.export.arn
}

#Notify
resource "aws_lambda_function" "notify" {
  filename         = "../src/notify.zip"
  function_name    = "${var.project_name}_notify"
  role             = aws_iam_role.notify.arn
  handler          = "main.main"
  source_code_hash = data.archive_file.notify.output_base64sha256
  runtime          = var.runtime
  layers           = ["arn:aws:lambda:eu-west-1:015030872274:layer:AWS-Parameters-and-Secrets-Lambda-Extension-Arm64:11", "arn:aws:lambda:eu-west-1:336392948345:layer:AWSSDKPandas-Python312-Arm64:16"]
  architectures    = ["arm64"]
  timeout          = "60"
  memory_size      = "512"

  environment {
    variables = {
      DYNAMODB_TABLE        = aws_dynamodb_table.data.id
      PROJECT_NAME          = var.project_name
      SNS_TOPIC             = "arn:aws:sns:${var.region}:${data.aws_caller_identity.current.account_id}:${var.sns_topic_name}"
      NOTIFICATIONS_ENABLED = var.notifications_enabled
    }
  }
}

resource "aws_lambda_permission" "allow_eventbridge_notify_weekly" {
  statement_id  = "AllowWeeklyExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notify.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.notify_weekly.arn
}

resource "aws_lambda_permission" "allow_eventbridge_notify_monthly" {
  statement_id  = "AllowMonthlyExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notify.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.notify_monthly.arn
}

#Nutrition
resource "aws_lambda_function" "nutrition" {
  filename         = "../src/nutrition.zip"
  function_name    = "${var.project_name}_nutrition"
  role             = aws_iam_role.nutrition.arn
  handler          = "main.main"
  source_code_hash = data.archive_file.nutrition.output_base64sha256
  runtime          = var.runtime
  layers           = ["arn:aws:lambda:eu-west-1:015030872274:layer:AWS-Parameters-and-Secrets-Lambda-Extension-Arm64:11", data.aws_lambda_layer_version.scipy.arn, data.aws_lambda_layer_version.requests.arn]
  architectures    = ["arm64"]
  timeout          = "60"
  memory_size      = "128"

  environment {
    variables = {
      PROJECT_NAME          = var.project_name
      SNS_TOPIC             = "arn:aws:sns:${var.region}:${data.aws_caller_identity.current.account_id}:${var.sns_topic_name}"
      NOTIFICATIONS_ENABLED = var.notifications_enabled
    }
  }
}