#!/usr/bin/env python3
# 实验结果方差分析脚本
# 用于分析多次运行结果的方差和统计显著性

import os
import json
import csv
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# 可选: scipy 用于统计检验
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("[警告] 未安装scipy。将跳过统计显著性检验。")
    print("         安装命令: pip install scipy")


def load_all_runs(base_dir: str, source: str, dataset: str, config: str, mode: str) -> List[Tuple[str, dict]]:
    """
    Load results.json from ALL runs (not just the latest) for a given configuration.
    Returns a list of (timestamp, results_dict) tuples.
    """
    mode_path = Path(base_dir) / source / dataset / config / mode
    
    if not mode_path.is_dir():
        print(f"[Warning] Directory not found for mode '{mode}': {mode_path}")
        return []
    
    runs = []
    timestamp_dirs = sorted([d for d in mode_path.iterdir() if d.is_dir()])
    
    for ts_dir in timestamp_dirs:
        results_file = ts_dir / "results.json"
        if results_file.is_file():
            try:
                with open(results_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                runs.append((ts_dir.name, data))
                print(f"  [✓] Loaded: {ts_dir.name}")
            except Exception as e:
                print(f"  [✗] Failed to load {results_file}: {e}")
    
    return runs


def extract_metrics(contract_data: dict) -> dict:
    """从单个合约的结果数据中提取关键指标"""
    return {
        'branch_coverage': contract_data.get('branch_coverage', {}).get('percentage', None),
        'code_coverage': contract_data.get('code_coverage', {}).get('percentage', None),
        'execution_time': contract_data.get('execution_time', None),
        'transactions_total': contract_data.get('transactions', {}).get('total', None),
        'transactions_per_sec': contract_data.get('transactions', {}).get('per_second', None),
        'memory_consumption': contract_data.get('memory_consumption', None),
    }


def compute_statistics(values: List[float]) -> dict:
    """为数值列表计算统计指标"""
    valid_values = [v for v in values if v is not None and not np.isnan(v)]
    
    if not valid_values:
        return {
            'mean': None, 'std': None, 'variance': None,
            'min': None, 'max': None, 'median': None,
            'n_runs': 0
        }
    
    arr = np.array(valid_values)
    return {
        'mean': float(np.mean(arr)),
        'std': float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        'variance': float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0,
        'min': float(np.min(arr)),
        'max': float(np.max(arr)),
        'median': float(np.median(arr)),
        'n_runs': len(valid_values)
    }


def aggregate_runs(runs: List[Tuple[str, dict]]) -> Dict[str, Dict[str, dict]]:
    """
    将多次运行的指标聚合为每个合约的统计数据
    返回: {contract_path: {metric_name: {mean, std, variance, min, max, median, n_runs}}}
    """
    # 首先，收集每个合约每个指标的所有数值
    contract_metrics = defaultdict(lambda: defaultdict(list))
    
    for timestamp, results in runs:
        for contract_path, contract_data in results.items():
            metrics = extract_metrics(contract_data)
            for metric_name, value in metrics.items():
                if value is not None:
                    contract_metrics[contract_path][metric_name].append(value)
    
    # Then compute statistics for each
    aggregated = {}
    for contract_path, metrics in contract_metrics.items():
        aggregated[contract_path] = {}
        for metric_name, values in metrics.items():
            aggregated[contract_path][metric_name] = compute_statistics(values)
    
    return aggregated


def compute_overall_statistics(aggregated: Dict[str, Dict[str, dict]], metric_name: str) -> dict:
    """
    Compute overall statistics across all contracts for a given metric.
    Uses the mean of each contract's mean values.
    """
    means = []
    stds = []
    
    for contract_path, metrics in aggregated.items():
        if metric_name in metrics and metrics[metric_name]['mean'] is not None:
            means.append(metrics[metric_name]['mean'])
            if metrics[metric_name]['std'] is not None:
                stds.append(metrics[metric_name]['std'])
    
    if not means:
        return {'overall_mean': None, 'overall_std': None, 'avg_within_contract_std': None}
    
    return {
        'overall_mean': float(np.mean(means)),
        'overall_std': float(np.std(means, ddof=1)) if len(means) > 1 else 0.0,
        'avg_within_contract_std': float(np.mean(stds)) if stds else None,
        'n_contracts': len(means)
    }


def perform_significance_test(
    aggregated_a: Dict[str, Dict[str, dict]], 
    aggregated_b: Dict[str, Dict[str, dict]],
    metric_name: str
) -> Optional[dict]:
    """
    Perform Wilcoxon signed-rank test comparing two modes.
    Uses the mean values from each contract.
    """
    if not SCIPY_AVAILABLE:
        return None
    
    # Get common contracts
    common_contracts = set(aggregated_a.keys()) & set(aggregated_b.keys())
    
    values_a = []
    values_b = []
    
    for contract in common_contracts:
        mean_a = aggregated_a[contract].get(metric_name, {}).get('mean')
        mean_b = aggregated_b[contract].get(metric_name, {}).get('mean')
        
        if mean_a is not None and mean_b is not None:
            values_a.append(mean_a)
            values_b.append(mean_b)
    
    if len(values_a) < 5:
        return {'error': f'Too few paired samples ({len(values_a)}) for statistical test'}
    
    try:
        # Wilcoxon signed-rank test (paired, non-parametric)
        statistic, p_value = stats.wilcoxon(values_a, values_b)
        
        # Also compute effect size (matched-pairs rank-biserial correlation)
        diff = np.array(values_b) - np.array(values_a)
        n = len(diff)
        
        # Cohen's d for paired samples
        mean_diff = np.mean(diff)
        std_diff = np.std(diff, ddof=1)
        cohens_d = mean_diff / std_diff if std_diff > 0 else 0
        
        return {
            'test': 'Wilcoxon signed-rank',
            'statistic': float(statistic),
            'p_value': float(p_value),
            'n_pairs': len(values_a),
            'significant_0.05': p_value < 0.05,
            'significant_0.01': p_value < 0.01,
            'cohens_d': float(cohens_d),
            'mean_improvement': float(np.mean(values_b) - np.mean(values_a))
        }
    except Exception as e:
        return {'error': str(e)}


def write_per_contract_csv(
    aggregated_results: Dict[str, Dict[str, Dict[str, dict]]],
    modes: List[str],
    output_path: Path
):
    """将详细的每个合约统计数据写入CSV文件"""
    
    metrics = ['branch_coverage', 'code_coverage', 'execution_time']
    
    # Build header
    header = ['Contract Path']
    for mode in modes:
        for metric in metrics:
            header.extend([
                f'{metric}_mean ({mode})',
                f'{metric}_std ({mode})',
                f'{metric}_min ({mode})',
                f'{metric}_max ({mode})',
                f'{metric}_n_runs ({mode})'
            ])
    
    # Get all contracts
    all_contracts = sorted(set().union(*[res.keys() for res in aggregated_results.values()]))
    
    rows = []
    for contract in all_contracts:
        row = [contract]
        for mode in modes:
            mode_data = aggregated_results.get(mode, {}).get(contract, {})
            for metric in metrics:
                stats = mode_data.get(metric, {})
                row.extend([
                    f"{stats.get('mean', 'N/A'):.2f}" if stats.get('mean') is not None else 'N/A',
                    f"{stats.get('std', 'N/A'):.2f}" if stats.get('std') is not None else 'N/A',
                    f"{stats.get('min', 'N/A'):.2f}" if stats.get('min') is not None else 'N/A',
                    f"{stats.get('max', 'N/A'):.2f}" if stats.get('max') is not None else 'N/A',
                    stats.get('n_runs', 0)
                ])
        rows.append(row)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    
    print(f"\n📄 每合约统计数据已保存至: {output_path}")


def write_summary_report(
    aggregated_results: Dict[str, Dict[str, Dict[str, dict]]],
    modes: List[str],
    significance_results: Dict[str, dict],
    run_counts: Dict[str, int],
    output_path: Path
):
    """写入包含总体统计和显著性检验的汇总报告"""
    
    metrics = ['branch_coverage', 'code_coverage', 'execution_time']
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("方差分析报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # 运行次数统计
        f.write("📊 每种模式的运行次数:\n")
        f.write("-" * 40 + "\n")
        for mode in modes:
            f.write(f"  {mode}: {run_counts.get(mode, 0)} 次运行\n")
        f.write("\n")
        
        # 每种模式的总体统计
        f.write("📈 总体统计 (所有合约):\n")
        f.write("-" * 80 + "\n")
        
        for metric in metrics:
            f.write(f"\n{metric.upper().replace('_', ' ')}:\n")
            f.write(f"{模式':<15} {'平均值':>10} {'标准差':>10} {'合约内平均标准差':>25} {'N':>5}\n")
            f.write("-" * 70 + "\n")
            
            for mode in modes:
                overall = compute_overall_statistics(aggregated_results[mode], metric)
                mean_str = f"{overall['overall_mean']:.2f}" if overall['overall_mean'] is not None else "N/A"
                std_str = f"{overall['overall_std']:.2f}" if overall['overall_std'] is not None else "N/A"
                within_std = f"{overall['avg_within_contract_std']:.2f}" if overall.get('avg_within_contract_std') is not None else "N/A"
                n_str = str(overall.get('n_contracts', 0))
                
                f.write(f"{mode:<15} {mean_str:>10} {std_str:>10} {within_std:>25} {n_str:>5}\n")
        
        # 显著性检验
        if significance_results:
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("📊 统计显著性检验\n")
            f.write("=" * 80 + "\n")
            
            for comparison, metrics_results in significance_results.items():
                f.write(f"\n{comparison}:\n")
                f.write("-" * 60 + "\n")
                
                for metric, result in metrics_results.items():
                    f.write(f"\n  {metric}:\n")
                    if 'error' in result:
                        f.write(f"    错误: {result['error']}\n")
                    else:
                        f.write(f"    检验方法: {result['test']}\n")
                        f.write(f"    样本对数: {result['n_pairs']}\n")
                        f.write(f"    p值: {result['p_value']:.6f}\n")
                        f.write(f"    显著 (α=0.05): {'是 ✓' if result['significant_0.05'] else '否'}\n")
                        f.write(f"    Significant (α=0.01): {'Yes ✓' if result['significant_0.01'] else 'No'}\n")
                        f.write(f"    Cohen's d: {result['cohens_d']:.3f}\n")
                        f.write(f"    Mean improvement: {result['mean_improvement']:.2f}\n")
        
        f.write("\n" + "=" * 80 + "\n")
        f.write("END OF REPORT\n")
        f.write("=" * 80 + "\n")
    
    print(f"📋 汇总报告已保存至: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze variance across multiple experiment runs.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--source', type=str, required=True,
                        help="Dataset source (e.g., 'curated', 'maxContract')")
    parser.add_argument('--dataset', type=str, required=True,
                        help="Dataset category (e.g., 'reentrancy', '150')")
    parser.add_argument('--config', type=str, required=True,
                        help="Configuration string (e.g., 'solc_v0.4.26-evm_byzantium-gen_10')")
    parser.add_argument('--modes', type=str, nargs='+', required=True,
                        help="Modes to analyze (e.g., baseline llm-full llm-cot)")
    parser.add_argument('--output-dir', type=str, default='variance_reports',
                        help="Directory to save output reports")
    parser.add_argument('--base-dir', type=str, default='experiments_results',
                        help="Base directory for experiment results")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("VARIANCE ANALYSIS FOR CONFUZZIUS EXPERIMENTS")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Source: {args.source}")
    print(f"  Dataset: {args.dataset}")
    print(f"  Config: {args.config}")
    print(f"  Modes: {', '.join(args.modes)}")
    print()
    
    # Load all runs for each mode
    aggregated_results = {}
    run_counts = {}
    
    for mode in args.modes:
        print(f"\n📂 Loading runs for mode: {mode}")
        runs = load_all_runs(args.base_dir, args.source, args.dataset, args.config, mode)
        
        if not runs:
            print(f"[Error] No runs found for mode '{mode}'. Skipping.")
            continue
        
        run_counts[mode] = len(runs)
        print(f"  Total runs loaded: {len(runs)}")
        
        aggregated_results[mode] = aggregate_runs(runs)
    
    if not aggregated_results:
        print("\n[Error] No valid results to analyze.")
        return
    
    # Perform significance tests if comparing multiple modes
    significance_results = {}
    if len(args.modes) >= 2 and SCIPY_AVAILABLE:
        print("\n📊 Performing statistical significance tests...")
        metrics = ['branch_coverage', 'code_coverage', 'execution_time']
        
        # Compare first mode (assumed baseline) against others
        baseline_mode = args.modes[0]
        for other_mode in args.modes[1:]:
            if baseline_mode in aggregated_results and other_mode in aggregated_results:
                comparison_key = f"{baseline_mode} vs {other_mode}"
                significance_results[comparison_key] = {}
                
                for metric in metrics:
                    result = perform_significance_test(
                        aggregated_results[baseline_mode],
                        aggregated_results[other_mode],
                        metric
                    )
                    if result:
                        significance_results[comparison_key][metric] = result
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_filename = f"variance_{args.source}_{args.dataset}_{args.config}_{'_vs_'.join(args.modes)}"
    
    # Write outputs
    write_per_contract_csv(
        aggregated_results, 
        args.modes,
        output_dir / f"{base_filename}_{timestamp}.csv"
    )
    
    write_summary_report(
        aggregated_results,
        args.modes,
        significance_results,
        run_counts,
        output_dir / f"{base_filename}_{timestamp}_summary.txt"
    )
    
    print("\n✅ 方差分析完成！")
    print(f"   报告已保存至: {output_dir}")


if __name__ == '__main__':
    main()
