#Replace the values in the console to keep them out of state + IaC
resource "aws_ssm_parameter" "app_creds" {
  for_each = var.app_creds

  name  = "/${var.project_name}/${each.key}"
  type  = "SecureString"
  value = "PLACEHOLDER"

  lifecycle {
    ignore_changes = [value]
  }
}