
# Roles and attachments
resource "aws_iam_role" "export" {
  name = "${var.project_name}_export"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "export_lambda_execution_role" {
  role       = aws_iam_role.export.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "export_dynamodb_read_write" {
  role       = aws_iam_role.export.name
  policy_arn = aws_iam_policy.dynamodb_read_write.arn
}

resource "aws_iam_role_policy_attachment" "export_ssm" {
  role       = aws_iam_role.export.name
  policy_arn = aws_iam_policy.ssm_kms.arn
}


resource "aws_iam_role" "notify" {
  name = "${var.project_name}_notify"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "notify_lambda_execution_role" {
  role       = aws_iam_role.notify.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "notify_dynamodb_query" {
  role       = aws_iam_role.notify.name
  policy_arn = aws_iam_policy.dynamodb_query.arn
}

resource "aws_iam_role_policy_attachment" "notify_sns_publish" {
  role       = aws_iam_role.notify.name
  policy_arn = aws_iam_policy.sns_publish.arn
}

resource "aws_iam_role_policy_attachment" "notify_ssm" {
  role       = aws_iam_role.notify.name
  policy_arn = aws_iam_policy.ssm_kms.arn
}

resource "aws_iam_role" "nutrition" {
  name = "${var.project_name}_nutrition"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "nutrition_lambda_execution_role" {
  role       = aws_iam_role.notify.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "nutrition_sns_publish" {
  role       = aws_iam_role.nutrition.name
  policy_arn = aws_iam_policy.sns_publish.arn
}

resource "aws_iam_role_policy_attachment" "nutrition_ssm" {
  role       = aws_iam_role.nutrition.name
  policy_arn = aws_iam_policy.ssm_kms.arn
}

#Policies

resource "aws_iam_policy" "ssm_kms" {
  name        = "${var.project_name}_ssm_kms"
  description = "A policy to allow access to SSM and associated KMS resources for the ${var.project_name} project."
  policy      = data.aws_iam_policy_document.ssm.json
}

resource "aws_iam_policy" "dynamodb_read_write" {
  name        = "${var.project_name}_ddb_rw"
  description = "A policy to read write access to DynamoDB for the ${var.project_name} project."
  policy      = data.aws_iam_policy_document.dynamodb_read_write.json
}

resource "aws_iam_policy" "dynamodb_query" {
  name        = "${var.project_name}_ddb_query"
  description = "A policy to run queries in DynamoDB for the ${var.project_name} project."
  policy      = data.aws_iam_policy_document.dynamodb_query.json
}

resource "aws_iam_policy" "sns_publish" {
  name        = "${var.project_name}_sns_publish"
  description = "A policy to publish to allow the ${var.project_name} project to publish to the notify SNS topic."
  policy      = data.aws_iam_policy_document.sns_publish.json
}

data "aws_iam_policy_document" "ssm" {
  statement {
    actions = ["ssm:GetParameter", "kms:Decrypt"]
    resources = [
      "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/*",
      data.aws_kms_key.ssm.arn
    ]
  }
}

data "aws_iam_policy_document" "dynamodb_read_write" {
  statement {
    actions   = ["dynamodb:DeleteItem", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.data.arn]
  }
}

data "aws_iam_policy_document" "dynamodb_query" {
  statement {
    actions   = ["dynamodb:Query"]
    resources = [aws_dynamodb_table.data.arn, "${aws_dynamodb_table.data.arn}/*"]
  }
}

data "aws_iam_policy_document" "sns_publish" {
  statement {
    actions   = ["sns:Publish"]
    resources = ["arn:aws:sns:${var.region}:${data.aws_caller_identity.current.account_id}:${var.sns_topic_name}"]
  }
}