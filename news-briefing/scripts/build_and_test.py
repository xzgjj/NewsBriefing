#!/usr/bin/env python3
"""构建与验证脚本。

功能:
  1. 检查 Python 版本 (>= 3.10)
  2. 检查依赖完整性
  3. 检查环境变量
  4. 检查配置文件合法性
  5. 运行 ruff check
  6. 运行 pytest
  7. 输出汇总报告
"""

import subprocess
import sys
from pathlib import Path


def check_python_version() -> bool:
    """检查 Python 版本。"""
    version = sys.version_info
    if version >= (3, 10):
        print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
        return True
    print(f"[FAIL] Python 版本过低: {version.major}.{version.minor} (需要 >= 3.10)")
    return False


def check_dependencies() -> bool:
    """检查 requirements.txt 中的依赖是否安装。"""
    req_path = Path("requirements.txt")
    if not req_path.exists():
        print("[SKIP] 未找到 requirements.txt")
        return True

    with open(req_path, "r") as f:
        requirements = [
            line.strip() for line in f
            if line.strip() and not line.startswith("#") and not line.startswith("-")
        ]

    # 包名到 import 名的映射
    import_map = {
        "pyyaml": "yaml",
        "beautifulsoup4": "bs4",
        "uvicorn[standard]": "uvicorn",
    }

    all_ok = True
    for req in requirements:
        pkg_name = req.split(">=")[0].split("==")[0].split("<")[0].split("~=")[0].strip()
        import_name = import_map.get(pkg_name, pkg_name.replace("-", "_"))
        try:
            __import__(import_name)
            print(f"[OK] {pkg_name}")
        except ImportError:
            print(f"[MISS] {pkg_name} — 请运行: pip install {req}")
            all_ok = False

    return all_ok


def check_env_vars() -> bool:
    """检查必要的环境变量。"""
    import os
    required_vars = {
        "TAVILY_API_KEY": "Tavily 搜索 API Key (可选，缺失时搜索功能降级)",
        "DEEPSEEK_API_KEY": "DeepSeek API Key (可选，缺失时使用规则兜底)",
    }

    all_ok = True
    for var, desc in required_vars.items():
        value = os.environ.get(var)
        if value:
            masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
            print(f"[OK] {var} = {masked}")
        else:
            if "可选" in desc:
                print(f"[WARN] {var} 未设置 — {desc}")
            else:
                print(f"[WARN] {var} 未设置 — {desc}")
                all_ok = False

    return all_ok


def check_config() -> bool:
    """检查配置文件合法性。"""
    config_paths = [
        Path("config.yaml"),
        Path("../config.yaml"),
    ]

    config_file = None
    for p in config_paths:
        if p.exists():
            config_file = p
            break

    if not config_file:
        print("[FAIL] 未找到 config.yaml")
        return False

    try:
        import yaml
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        print(f"[OK] config.yaml 解析成功 ({config_file})")
        print(f"     版本: {data.get('version', 'N/A')}")
        print(f"     信源: Tier1={len(data.get('sources', {}).get('tier1', []))}, "
              f"Tier2={len(data.get('sources', {}).get('tier2', []))}")
        return True
    except Exception as e:
        print(f"[FAIL] config.yaml 解析失败: {e}")
        return False


def run_ruff() -> bool:
    """运行 ruff 检查。"""
    print("\n--- ruff check ---")
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/", "tests/"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("[OK] ruff check 通过")
        return True
    else:
        print(result.stdout)
        print(result.stderr)
        print("[FAIL] ruff check 发现错误")
        return False


def run_pytest() -> bool:
    """运行测试。"""
    print("\n--- pytest ---")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        capture_output=True, text=True,
    )
    print(result.stdout[-2000:])  # 最后2000字符
    if result.returncode == 0:
        print("[OK] 所有测试通过")
        return True
    else:
        print("[FAIL] 测试未通过")
        return False


def main() -> int:
    """主函数。"""
    print("=" * 60)
    print("  NewsBriefing 构建与验证")
    print("=" * 60)

    results: dict[str, bool] = {}

    # 1. Python 版本
    print("\n[1/5] 检查 Python 版本...")
    results["python"] = check_python_version()

    # 2. 依赖
    print("\n[2/5] 检查依赖完整性...")
    results["deps"] = check_dependencies()

    # 3. 环境变量
    print("\n[3/5] 检查环境变量...")
    results["env"] = check_env_vars()

    # 4. 配置
    print("\n[4/5] 检查配置文件...")
    results["config"] = check_config()

    # 5. ruff + pytest
    print("\n[5/5] 代码质量与测试...")
    results["ruff"] = run_ruff()
    results["pytest"] = run_pytest()

    # 汇总
    print("\n" + "=" * 60)
    print("  汇总报告")
    print("=" * 60)
    for check, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {check}")

    all_ok = all(results.values())
    if all_ok:
        print("\n✅ 所有检查通过！项目可以正常运行。")
        return 0
    else:
        print("\n❌ 部分检查未通过，请修复后再试。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
