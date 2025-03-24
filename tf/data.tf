# Get current AWS account details
data "aws_caller_identity" "current" {}

# Lambda layer created outside of this repo. Simple Lambda layer with just the requests package.
data "aws_lambda_layer_version" "requests" {
  layer_name = "requests"
}

# Lambda layer created outside of this repo. This contains a trimmed down scipy to get around the size limits of Lambda layers. 
# The steps here can be used https://korniichuk.medium.com/lambda-with-pandas-fd81aa2ff25e.
data "aws_lambda_layer_version" "scipy" {
  layer_name = "scipy"
}

# Add each function to a zip file.
data "archive_file" "export" {
  type        = "zip"
  source_dir  = "../src/export"
  output_path = "../src/export.zip"
}

data "archive_file" "notify" {
  type        = "zip"
  source_dir  = "../src/notify"
  output_path = "../src/notify.zip"
}

data "archive_file" "nutrition" {
  type        = "zip"
  source_dir  = "../src/nutrition"
  output_path = "../src/nutrition.zip"
}

# Get key ID for SSM key
data "aws_kms_key" "ssm" {
  key_id = "alias/aws/ssm"
}