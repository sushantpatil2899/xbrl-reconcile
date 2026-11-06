output "bucket_name" {
  value = b2_bucket.raw.bucket_name
}

output "s3_endpoint" {
  value = data.b2_account_info.current.s3_api_url
}

# The hostname Azure generates for the app. Needed to reach the API at all, and the
# target the Datadog synthetic tests will be pointed at.
output "api_hostname" {
  value = azurerm_container_app.api.ingress[0].fqdn
}

output "api_url" {
  value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}
