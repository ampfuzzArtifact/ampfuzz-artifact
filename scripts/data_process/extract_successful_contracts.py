# 提取成功合约脚本
# 用于从实验结果中提取成功执行的合约文件
import json
import os
import shutil
from datetime import datetime


# 记录：2094下执行结果为 944
def extract_successful_contracts(results_file, output_dir=None):
    """提取成功执行的合约文件
    
    Args:
        results_file: results.json 的路径
        output_dir: 输出目录，默认为 'successful_contracts_{timestamp}'
    """
    # 设置输出目录
    if output_dir is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        output_dir = f"successful_contracts_{timestamp}"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 读取 results.json
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # 统计信息
    total_contracts = len(results)
    copied_contracts = 0
    skipped_contracts = 0
    errors = []
    
    print(f"\n🔍 从 {results_file} 中提取成功合约")
    print(f"📁 输出目录: {output_dir}\n")

    # 处理每个合约
    for contract_path in results.keys():
        try:
            # 检查原始文件是否存在
            if not os.path.exists(contract_path):
                print(f"❌ Source file not found: {contract_path}")
                skipped_contracts += 1
                continue
                
            # 获取相对路径结构
            rel_path = os.path.relpath(contract_path, "dataset")
            new_path = os.path.join(output_dir, rel_path)
            
            # 创建必要的子目录
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            
            # 复制文件
            shutil.copy2(contract_path, new_path)
            copied_contracts += 1
            print(f"✅ Copied: {rel_path}")
            
        except Exception as e:
            errors.append((contract_path, str(e)))
            skipped_contracts += 1
            print(f"❌ Error processing {contract_path}: {e}")
    
    # 保存统计信息
    stats = {
        "timestamp": datetime.now().isoformat(),
        "source_file": results_file,
        "total_contracts": total_contracts,
        "copied_contracts": copied_contracts,
        "skipped_contracts": skipped_contracts,
        "errors": [{"file": f, "error": e} for f, e in errors]
    }
    
    with open(os.path.join(output_dir, "extraction_stats.json"), 'w') as f:
        json.dump(stats, f, indent=2)
    
    # 打印总结
    print(f"\n📊 Summary:")
    print(f"{'Total contracts:':<20} {total_contracts}")
    print(f"{'Successfully copied:':<20} {copied_contracts}")
    print(f"{'Skipped/Errors:':<20} {skipped_contracts}")
    print(f"\n💾 Statistics saved to {os.path.join(output_dir, 'extraction_stats.json')}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract successfully executed contracts')
    parser.add_argument('results_file', help='Path to results.json')
    parser.add_argument('--output-dir', help='Output directory (optional)')
    
    args = parser.parse_args()
    
    extract_successful_contracts(args.results_file, args.output_dir)