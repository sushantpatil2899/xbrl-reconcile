output "bucket_name" {
  value = b2_bucket.raw.bucket_name
}

output "s3_endpoint" {
  value = data.b2_account_info.current.s3_api_url
}
