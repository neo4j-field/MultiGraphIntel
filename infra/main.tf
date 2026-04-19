# Terraform for Multi-Graph Intel Multi-Agent System

variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP Region"
  type        = string
  default     = "us-central1"
}

variable "service_account_name" {
  description = "Name of the graph intelligence service account"
  type        = string
  default     = "graph-intel-sa"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Enable Required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",      # Vertex AI Agent Builder
    "bigquery.googleapis.com",        # BigQuery Graph
    "spanner.googleapis.com",         # Spanner Graph
    "secretmanager.googleapis.com",   # Neo4j Aura Credentials
    "dataflow.googleapis.com",        # BQ -> Neo4j Migration
    "iam.googleapis.com",             # Service Account Management
    "compute.googleapis.com"          # Supporting compute for Cloud Run shim
  ])
  service = each.key
  disable_on_destroy = false
}

# 2. Create Service Account
resource "google_service_account" "graph_intel_sa" {
  account_id   = var.service_account_name
  display_name = "Graph Intelligence Service Account"
  project      = var.project_id
}

# 3. Least-Privilege IAM Roles
resource "google_project_iam_member" "bigquery_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.graph_intel_sa.email}"
}

resource "google_project_iam_member" "bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.graph_intel_sa.email}"
}

resource "google_project_iam_member" "spanner_database_user" {
  project = var.project_id
  role    = "roles/spanner.databaseUser"
  member  = "serviceAccount:${google_service_account.graph_intel_sa.email}"
}

resource "google_project_iam_member" "secret_manager_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.graph_intel_sa.email}"
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.graph_intel_sa.email}"
}

# 4. Neo4j & MCP Secrets
resource "google_secret_manager_secret" "neo4j_uri" {
  secret_id = "neo4j-uri"
  project   = var.project_id
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "neo4j_username" {
  secret_id = "neo4j-username"
  project   = var.project_id
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "neo4j_password" {
  secret_id = "neo4j-password"
  project   = var.project_id
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "mcp_client_id" {
  secret_id = "mcp-client-id"
  project   = var.project_id
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "mcp_client_secret" {
  secret_id = "mcp-client-secret"
  project   = var.project_id
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret" "mcp_endpoint" {
  secret_id = "mcp-endpoint"
  project   = var.project_id
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# 5. Outputs
output "service_account_email" {
  value = google_service_account.graph_intel_sa.email
}
