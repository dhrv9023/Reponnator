#!/usr/bin/env python3
"""
Test full CodeAutopsy pipeline on a fresh repository
"""
import subprocess
import sys
import json
from pathlib import Path

def run_command(cmd, cwd="/home/ag2/Desktop/github_prj/codeautopsy"):
    """Run command and return output"""
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0, result.stdout, result.stderr

def test_pipeline(github_url):
    """Test full pipeline on a GitHub URL"""
    print(f"\n🚀 Testing CodeAutopsy pipeline on: {github_url}")
    
    # Extract repo key
    parts = github_url.rstrip('/').split('/')
    owner, repo = parts[-2], parts[-1]
    repo_key = f"{owner}/{repo}"
    
    print(f"📦 Repository: {repo_key}")
    
    # Step 1: Full pipeline run
    print("\n📥 Step 1: Running full pipeline (ingest + parse + embed)...")
    success, stdout, stderr = run_command([
        "python3", "main.py", "run", github_url
    ])
    
    if not success:
        print("❌ Pipeline failed!")
        return False
    
    print("✅ Pipeline completed successfully")
    
    # Step 2: Generate diagram
    print("\n📊 Step 2: Generating diagram...")
    success, stdout, stderr = run_command([
        "python3", "main.py", "diagram", repo_key, "--force"
    ])
    
    if not success:
        print("❌ Diagram generation failed!")
        return False
    
    print("✅ Diagram generated successfully")
    
    # Step 3: Generate story
    print("\n📖 Step 3: Generating story...")
    success, stdout, stderr = run_command([
        "python3", "main.py", "story", repo_key, "--force"
    ])
    
    if not success:
        print("❌ Story generation failed!")
        return False
    
    print("✅ Story generated successfully")
    
    # Verify outputs
    print("\n🔍 Step 4: Verifying outputs...")
    
    repo_folder = Path(f"/home/ag2/Desktop/github_prj/codeautopsy/data/repos/{owner}__{repo}")
    
    diagram_file = repo_folder / "diagram" / "mermaid_diagram.mmd"
    story_file = repo_folder / "story" / "story_output.json"
    
    if diagram_file.exists():
        print(f"✅ Diagram file exists: {diagram_file}")
        # Read and display stats
        with open(repo_folder / "diagram" / "diagram_metadata.json") as f:
            diagram_meta = json.load(f)
            print(f"   - Nodes: {diagram_meta.get('total_nodes', 0)}")
            print(f"   - Edges: {diagram_meta.get('total_edges', 0)}")
    else:
        print(f"❌ Diagram file missing: {diagram_file}")
    
    if story_file.exists():
        print(f"✅ Story file exists: {story_file}")
        # Read and display stats
        with open(story_file) as f:
            story_data = json.load(f)
            print(f"   - Title: {story_data.get('title', 'N/A')}")
            print(f"   - Sections: {len(story_data.get('sections', []))}")
    else:
        print(f"❌ Story file missing: {story_file}")
    
    print("\n" + "="*60)
    print("✅ FULL PIPELINE TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    
    return True

if __name__ == "__main__":
    # Test with a small, well-structured repository
    test_repos = [
        "https://github.com/pallets/itsdangerous",  # Small Python library
    ]
    
    if len(sys.argv) > 1:
        # Custom URL provided
        test_repos = [sys.argv[1]]
    
    for repo_url in test_repos:
        success = test_pipeline(repo_url)
        if not success:
            print(f"\n❌ Test failed for {repo_url}")
            sys.exit(1)
    
    print("\n🎉 All tests passed!")
