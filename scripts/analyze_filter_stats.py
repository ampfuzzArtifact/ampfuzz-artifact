#!/usr/bin/env python3
# 分析LLM种子过滤统计数据的脚本
import json
import os
import argparse
from collections import defaultdict
from datetime import datetime


def load_filter_stats(log_path):
    """从 JSONL 文件加载过滤统计数据"""
    records = []
    if not os.path.exists(log_path):
        print(f"Warning: Filter stats file not found: {log_path}")
        return records
    
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line: {e}")
    
    return records


def analyze_stats(records):
    """分析过滤统计数据"""
    if not records:
        return None
    
    # 聚合统计
    total_generated = sum(r.get("total_generated", 0) for r in records)
    total_accepted = sum(r.get("total_accepted", 0) for r in records)
    total_rejected = sum(r.get("total_rejected", 0) for r in records)
    
    # 按拒绝原因聚合
    rejection_reasons = defaultdict(int)
    for r in records:
        reasons = r.get("rejection_reasons", {})
        for reason, count in reasons.items():
            rejection_reasons[reason] += count
    
    # 计算比例
    filter_rate = (total_rejected / total_generated * 100) if total_generated > 0 else 0.0
    
    # 拒绝原因分布（占被拒绝总数的比例）
    reason_distribution = {}
    if total_rejected > 0:
        for reason, count in rejection_reasons.items():
            reason_distribution[reason] = {
                "count": count,
                "percent_of_rejected": round(count / total_rejected * 100, 2),
                "percent_of_total": round(count / total_generated * 100, 2)
            }
    
    # 按合约统计（注意：合约地址可能是测试部署地址，不是唯一的）
    per_contract_stats = {}
    for r in records:
        contract = r.get("contract", "unknown")
        if contract not in per_contract_stats:
            per_contract_stats[contract] = {
                "total_generated": 0,
                "total_accepted": 0,
                "total_rejected": 0
            }
        per_contract_stats[contract]["total_generated"] += r.get("total_generated", 0)
        per_contract_stats[contract]["total_accepted"] += r.get("total_accepted", 0)
        per_contract_stats[contract]["total_rejected"] += r.get("total_rejected", 0)
    
    # 注意：由于合约地址是测试部署地址，实际合约数量应该看records数量
    # 每个record代表一次LLM会话结束时的统计
    num_llm_sessions = len(records)
    
    return {
        "summary": {
            "total_contracts": len(per_contract_stats),  # 唯一合约地址数（可能为1）
            "total_llm_sessions": num_llm_sessions,      # LLM 会话数（更有意义）
            "total_records": len(records),
            "total_generated": total_generated,
            "total_accepted": total_accepted,
            "total_rejected": total_rejected,
            "filter_rate_percent": round(filter_rate, 2),
            "acceptance_rate_percent": round(100 - filter_rate, 2)
        },
        "rejection_reasons": dict(rejection_reasons),
        "reason_distribution": reason_distribution,
        "per_contract_stats": per_contract_stats
    }


def generate_text_report(analysis):
    """生成文本统计报告"""
    if not analysis:
        return "无可用数据进行分析"
    
    s = analysis["summary"]
    lines = [
        "=" * 60,
        "          LLM过滤统计分析报告",
        "=" * 60,
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "统计概览",
        "-" * 40,
        f"  总LLM会话数:               {s.get('total_llm_sessions', s['total_records'])}",
        "",
        f"  LLM生成种子总数:           {s['total_generated']}",
        f"  已接受种子数:             {s['total_accepted']}",
        f"  已拒绝种子数:             {s['total_rejected']}",
        "",
        f"  过滤率:                   {s['filter_rate_percent']:.2f}%",
        f"  接受率:                   {s['acceptance_rate_percent']:.2f}%",
        "",
        "拒绝原因分布",
        "-" * 40,
    ]
    
    rd = analysis.get("reason_distribution", {})
    # 按数量排序
    sorted_reasons = sorted(rd.items(), key=lambda x: x[1]["count"], reverse=True)
    
    # 映射原因名称为中文
    reason_names = {
        "invalid_format": "无效格式 (参数非列表类型)",
        "abi_mismatch": "ABI/函数不匹配",
        "type_sanitize_fail": "类型转换失败",
        "arg_count_mismatch": "参数数量不匹配",
        "json_parse_fail": "JSON解析失败"
    }
    
    for reason, stats in sorted_reasons:
        readable_name = reason_names.get(reason, reason)
        lines.append(f"  {readable_name}:")
        lines.append(f"    数量: {stats['count']}")
        lines.append(f"    占拒绝总数比例: {stats['percent_of_rejected']:.1f}%")
        lines.append(f"    占总数比例:     {stats['percent_of_total']:.1f}%")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze LLM seed filter statistics")
    parser.add_argument(
        "--log", 
        default="ConFuzzius/experiments_results/filter_stats.jsonl",
        help="Path to filter_stats.jsonl file"
    )
    parser.add_argument(
        "--output", 
        default="ConFuzzius/scripts/filter_analysis/output",
        help="Output directory for reports"
    )
    args = parser.parse_args()
    
    # 处理相对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    
    log_path = args.log
    if not os.path.isabs(log_path):
        log_path = os.path.join(project_root, log_path)
    
    output_dir = args.output
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(project_root, output_dir)
    
    print(f"正在加载过滤统计数据: {log_path}")
    records = load_filter_stats(log_path)
    print(f"已加载 {len(records)} 条记录")
    
    analysis = analyze_stats(records)
    
    if not analysis:
        print("无可分析数据。请先运行实验。")
        return
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存 JSON 报告
    json_path = os.path.join(output_dir, "filter_analysis_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"JSON报告已保存至: {json_path}")
    
    # 保存文本报告
    text_report = generate_text_report(analysis)
    txt_path = os.path.join(output_dir, "filter_analysis_report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_report)
    print(f"文本报告已保存至: {txt_path}")
    print("\n" + text_report)


if __name__ == "__main__":
    main()
