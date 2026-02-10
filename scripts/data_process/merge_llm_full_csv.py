# 合并LLM-full CSV文件脚本
# 用于将llm-full结果合并到多模式比较CSV中
import pandas as pd
import argparse
import os

def load_csv(path):
    """加载CSV文件，兼容注释行"""
    df = pd.read_csv(path)
    # 兼容可能带有注释首行 // filepath:
    if df.columns[0].startswith("// filepath"):
        df = pd.read_csv(path, skiprows=1)
    return df

def main():
    parser = argparse.ArgumentParser(description="将llm-full CSV合并到多模式比较CSV中。")
    parser.add_argument("--base-csv", required=True,
                        help="包含baseline/llm-cot/llm-mutate列的CSV。")
    parser.add_argument("--llm-full-csv", required=True,
                        help="包含llm-full列的CSV。")
    parser.add_argument("--output", required=False,
                        help="输出CSV路径。默认: <base>_merged_llm-full.csv")
    args = parser.parse_args()

    base_df = load_csv(args.base_csv)
    full_df = load_csv(args.llm_full_csv)

    # 规范列名
    key_col = "Contract Path"
    if key_col not in base_df.columns or key_col not in full_df.columns:
        raise ValueError(f"文件中缺少 '{key_col}' 列。")

    # 仅保留 llm-full 需要的列
    expected_full_cols = [
        key_col,
        "Branch Coverage (llm-full)",
        "Code Coverage (llm-full)",
        "Execution Time (llm-full)"
    ]
    missing = [c for c in expected_full_cols if c not in full_df.columns]
    if missing:
        raise ValueError(f"Llm-full CSV缺少列: {missing}")

    full_df = full_df[expected_full_cols]

    # 去重（若有重复，取首次出现）
    base_df = base_df.drop_duplicates(subset=[key_col], keep="first")
    full_df = full_df.drop_duplicates(subset=[key_col], keep="first")

    # 合并（外连接：保留所有合约；若只想交集改 how='inner'）
    merged = pd.merge(base_df, full_df, on=key_col, how="left")

    # 输出路径
    if args.output:
        out_path = args.output
    else:
        root, ext = os.path.splitext(args.base_csv)
        out_path = root + "_merged_llm-full" + ext

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    merged.to_csv(out_path, index=False, encoding="utf-8")

    print(f"合并行数: {len(merged)}")
    missing_full = merged[merged["Branch Coverage (llm-full)"].isna()].shape[0]
    if missing_full:
        print(f"警告: {missing_full} 个合约在llm-full CSV中未找到。")
    print(f"已写入: {out_path}")

if __name__ == "__main__":
    main()
