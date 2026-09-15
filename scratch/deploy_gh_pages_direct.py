import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')

def deploy_gh_pages():
    print("=== Deploying Updated 82 Streams (with Real Broadcast Dates) to gh-pages ===")
    
    # 1. Run static export
    subprocess.run([sys.executable, "-m", "scratch.export_static_gh_pages"], check=True)
    
    dist_dir = os.path.abspath("dist")
    if not os.path.exists(dist_dir):
        print("❌ Error: dist/ directory does not exist!")
        return

    # 2. Push to origin gh-pages using git worktree or temp repo
    tmp_repo = tempfile.mkdtemp(prefix="gh_pages_deploy_")
    try:
        subprocess.run(["git", "init"], cwd=tmp_repo, check=True)
        subprocess.run(["git", "checkout", "-b", "gh-pages"], cwd=tmp_repo, check=True)

        for item in os.listdir(dist_dir):
            s = os.path.join(dist_dir, item)
            d = os.path.join(tmp_repo, item)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        subprocess.run(["git", "add", "-A"], cwd=tmp_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat(deploy): publish 82 streams with exact real YouTube broadcast dates"], cwd=tmp_repo, check=True)
        
        repo_url = "https://github.com/mting314/vtuber-larping.git"
        subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=tmp_repo, check=True)
        
        res = subprocess.run(["git", "push", "-f", "origin", "gh-pages"], cwd=tmp_repo, capture_output=True, text=True)
        if res.returncode == 0:
            print("🎉 SUCCESS! Force-pushed updated 82 streams to origin/gh-pages!")
        else:
            print(f"❌ Git push failed: {res.stderr}")
    finally:
        shutil.rmtree(tmp_repo, ignore_errors=True)

if __name__ == "__main__":
    deploy_gh_pages()
