import os

def setup_sonar_and_github():
    # Коренева папка твого проекту
    base_dir = r"C:\Users\Acer Nitro 5\Desktop\Axis_OS"
    
    # 1. СТВОРЕННЯ ФАЙЛУ sonar-project.properties
    properties_content = """# Required metadata
sonar.projectKey=Axis_OS_Local
sonar.projectName=Axis_OS_Local
sonar.projectVersion=1.0.0

# Path to the source directories
sonar.sources=/usr/src
sonar.sourceEncoding=UTF-8
sonar.python.version=3.12

# Exclusions
sonar.exclusions=sonarqube-26.4.0.121862/**, dist/**, build/**, .git/**, **/assets/sounds/**
"""
    
    properties_path = os.path.join(base_dir, "sonar-project.properties")
    with open(properties_path, "w", encoding="utf-8") as f:
        f.write(properties_content)
    print(f"✅ Створено: {properties_path}")


    # 2. СТВОРЕННЯ СТРУКТУРИ ГІТХАБА ТА build.yml
    workflow_dir = os.path.join(base_dir, ".github", "workflows")
    os.makedirs(workflow_dir, exist_ok=True)
    
    yaml_content = """name: Build
on:
  push:
    branches:
      - main
      - master
jobs:
  build:
    name: Build and analyze
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Shallow clones should be disabled for a better relevancy of analysis
          
      - uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
"""
    
    yaml_path = os.path.join(workflow_dir, "build.yml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"✅ Створено: {yaml_path}")
    
    print("\n🚀 Все готово! Тепер файли лежать там, де треба.")
    print("👉 Залишилося зробити git push у PowerShell.")

if __name__ == "__main__":
    setup_sonar_and_github()