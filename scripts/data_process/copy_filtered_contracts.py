# 复制过滤后合约文件脚本
# 用于将过滤后CSV中列出的合约复制到新文件夹
import os
import csv
import argparse
import shutil

def collect_contract_paths(csv_path):
    """从CSV文件中收集合约路径"""
    contracts = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            # 跳过注释/表头
            if row[0].startswith("//") or row[0].startswith("Contract Path"):
                continue
            contract_path = row[0].strip()
            if contract_path and contract_path.endswith(".sol"):
                contracts.append(contract_path)
    return contracts

def copy_contracts(contract_paths, dst_dir):
    """复制合约文件到目标目录"""
    os.makedirs(dst_dir, exist_ok=True)
    copied, missing = 0, 0
    for path in contract_paths:
        if not os.path.exists(path):
            print(f"[缺失] {path}")
            missing += 1
            continue
        filename = os.path.basename(path)
        dst_path = os.path.join(dst_dir, filename)
        shutil.copy2(path, dst_path)
        copied += 1
    return copied, missing

def main():
    parser = argparse.ArgumentParser(description="将过滤后比较CSV中列出的合约复制到新文件夹")
    parser.add_argument("-i", "--input-csv", required=True, help="过滤后的比较CSV路径")
    parser.add_argument("-d", "--dst-dir", default="dataset/maxContract/150_new", help="目标目录")
    args = parser.parse_args()

    contract_paths = collect_contract_paths(args.input_csv)
    print(f"在CSV中找到 {len(contract_paths)} 个合约条目。")
    copied, missing = copy_contracts(contract_paths, args.dst_dir)
    print(f"已复制: {copied}, 缺失: {missing}, 输出目录: {args.dst_dir}")

if __name__ == "__main__":
    main()
