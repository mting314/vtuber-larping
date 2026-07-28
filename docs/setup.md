# ⚙️ Setup & Deployment Guide

This guide covers local environment setup, GCP Vertex AI configuration, and GitHub Pages deployment.

---

## 🛠️ Local Environment Setup

### 1. Requirements
* Python 3.12+
* Google Cloud SDK (`gcloud`)

### 2. Environment Setup with `uv`
```bash
# Install uv package manager if needed
pip install uv

# Install dependencies and sync environment
uv sync
```

### 3. GCP Vertex AI Configuration
1. Create a dedicated GCP Project (e.g. `vtuber-digest-503801`).
2. Enable the **Vertex AI API** (`aiplatform.googleapis.com`).
3. Set your project ID in [.env](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/.env):
   ```env
   GCP_PROJECT=vtuber-digest-503801
   GCP_LOCATION=us-central1
   ```

---

## 🚀 Deployment to GitHub Pages

1. Open your repository Pages settings: **[GitHub Pages Settings](https://github.com/mting314/vtuber-larping/settings/pages)**
2. Under **Build and deployment → Source**, select **`GitHub Actions`**.
3. Push to `main` branch. The [.github/workflows/deploy-pages.yml](file:///c:/Users/Michael/Documents/GitHub/vtuber-larping/.github/workflows/deploy-pages.yml) workflow will automatically build static JSON artifacts and deploy to **`https://mting314.github.io/vtuber-larping/`**.
