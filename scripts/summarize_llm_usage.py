# LLM使用情况汇总脚本
# 用于统计LLM调用的token消耗情况
import json, os, argparse
from collections import defaultdict

def main(log_path, out_path):
    stats = defaultdict(lambda: {
        "total": {"prompt":0,"completion":0,"total":0,"calls":0},
        "init": {"prompt":0,"completion":0,"total":0,"calls":0},
        "mutation": {"prompt":0,"completion":0,"total":0,"calls":0},
    })
    if not os.path.exists(log_path):
        print(f"文件未找到: {log_path}")
        return
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            rec = json.loads(line)
            c = rec.get("contract","unknown")
            phase = rec.get("phase","init")
            p = int(rec.get("prompt_tokens",0))
            m = int(rec.get("completion_tokens",0))
            t = int(rec.get("total_tokens", p+m))
            # 总计
            stats[c]["total"]["prompt"] += p
            stats[c]["total"]["completion"] += m
            stats[c]["total"]["total"] += t
            stats[c]["total"]["calls"] += 1
            # 分阶段
            if phase not in stats[c]:
                stats[c][phase] = {"prompt":0,"completion":0,"total":0,"calls":0}
            stats[c][phase]["prompt"] += p
            stats[c][phase]["completion"] += m
            stats[c][phase]["total"] += t
            stats[c][phase]["calls"] += 1

    # 计算总体均值/中位数等（简版）
    per_contract_totals = [v["total"]["total"] for v in stats.values()]
    summary = {
        "contracts": stats,
        "global": {
            "num_contracts": len(per_contract_totals),
            "mean_total_tokens_per_contract": (sum(per_contract_totals)/len(per_contract_totals)) if per_contract_totals else 0
        }
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"已写入: {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="ConFuzzius/experiments_results/llm_usage.jsonl")
    parser.add_argument("--out", default="ConFuzzius/experiments_results/llm_usage_summary.json")
    args = parser.parse_args()
    main(args.log, args.out)