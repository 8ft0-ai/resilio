terraform {
  backend "gcs" {
    bucket = "resilio-control-e882d4-tfstate"
    prefix = "bootstrap"
  }
}
