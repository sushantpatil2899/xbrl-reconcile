data "b2_account_info" "current" {}

resource "b2_bucket" "raw" {
  bucket_name = var.bucket_name
  bucket_type = "allPrivate"

  # The state file is rewritten every run and B2 keeps old versions of
  # overwritten files. Delete those old versions after 30 days.
  lifecycle_rules {
    file_name_prefix             = "raw/sec/_state/"
    days_from_hiding_to_deleting = 30
  }

  # The database is rewritten by every transform run, at about 21 MB a time.
  # Without this, a year of daily runs would leave 365 hidden copies and fill
  # the free tier. Seven days is enough to roll back a bad build.
  lifecycle_rules {
    file_name_prefix             = "warehouse/"
    days_from_hiding_to_deleting = 7
  }
}

# Key used by the daily workflow. Limited to this bucket and cannot delete files.
resource "b2_application_key" "ingest" {
  key_name     = "${var.github_repository}-ingest"
  bucket_ids   = [b2_bucket.raw.bucket_id]
  capabilities = ["listBuckets", "listFiles", "readFiles", "writeFiles"]
}

resource "github_actions_secret" "b2_ingest_key_id" {
  repository  = var.github_repository
  secret_name = "B2_INGEST_KEY_ID"
  value       = b2_application_key.ingest.application_key_id
}

resource "github_actions_secret" "b2_ingest_key" {
  repository  = var.github_repository
  secret_name = "B2_INGEST_KEY"
  value       = b2_application_key.ingest.application_key
}

resource "github_actions_secret" "sec_contact_email" {
  repository  = var.github_repository
  secret_name = "SEC_CONTACT_EMAIL"
  value       = var.sec_contact_email
}

resource "github_actions_variable" "b2_bucket" {
  repository    = var.github_repository
  variable_name = "B2_BUCKET"
  value         = b2_bucket.raw.bucket_name
}

resource "github_actions_variable" "b2_endpoint" {
  repository    = var.github_repository
  variable_name = "B2_ENDPOINT"
  value         = data.b2_account_info.current.s3_api_url
}
