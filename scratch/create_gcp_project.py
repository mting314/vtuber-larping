import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

def run_gcloud(args):
    cmd = ["gcloud.cmd", "--quiet"] + args
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:", res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)
    return res

def main():
    project_id = "vtuber-digest-2026"
    
    print(f"=== Creating Dedicated GCP Project: {project_id} ===")
    
    # 1. Create GCP Project
    run_gcloud(["projects", "create", project_id, "--name=VTuber Digest"])
    
    # 2. Set active project
    run_gcloud(["config", "set", "project", project_id])

    # 3. Enable Service Usage & Vertex AI API
    print(f"\n=== Enabling Vertex AI API on {project_id} ===")
    run_gcloud(["services", "enable", "aiplatform.googleapis.com", "--project", project_id])

if __name__ == "__main__":
    main()
