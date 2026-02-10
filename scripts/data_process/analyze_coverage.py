# 覆盖率分析脚本
# 用于分析和提取覆盖率改进的合约
import pandas as pd
import os

def analyze_and_extract_improvements():
    # 读取CSV文件
    df = pd.read_csv('comparison_reports/comparison_2094_new_solc_v0.4.26-evm_byzantium-gen_10_baseline_vs_llm-mutate.csv')
    
    # 转换百分比字符串为浮点数
    df['Branch Coverage (baseline)'] = df['Branch Coverage (baseline)'].str.rstrip('%').astype(float)
    df['Branch Coverage (llm-mutate)'] = df['Branch Coverage (llm-mutate)'].str.rstrip('%').astype(float)
    df['Code Coverage (baseline)'] = df['Code Coverage (baseline)'].str.rstrip('%').astype(float)
    df['Code Coverage (llm-mutate)'] = df['Code Coverage (llm-mutate)'].str.rstrip('%').astype(float)
    
    # 找出表现更好的案例并计算改进幅度
    branch_improvements = df[df['Branch Coverage (llm-mutate)'] > df['Branch Coverage (baseline)']].copy()
    code_improvements = df[df['Code Coverage (llm-mutate)'] > df['Code Coverage (baseline)']].copy()
    
    branch_improvements['Improvement'] = (
        branch_improvements['Branch Coverage (llm-mutate)'] - 
        branch_improvements['Branch Coverage (baseline)']
    )
    
    code_improvements['Improvement'] = (
        code_improvements['Code Coverage (llm-mutate)'] - 
        code_improvements['Code Coverage (baseline)']
    )
    
    # 按改进幅度排序
    branch_improvements = branch_improvements.sort_values('Improvement', ascending=False)
    code_improvements = code_improvements.sort_values('Improvement', ascending=False)
    
    # 创建输出目录
    output_dir = 'comparison_reports/improved_contracts'
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存分析结果
    with open(f'{output_dir}/improvement_analysis.txt', 'w') as f:
        f.write("Coverage Improvement Analysis\n")
        f.write("===========================\n\n")
        
        f.write(f"Total Contracts Analyzed: {len(df)}\n\n")
        
        # Branch Coverage 详细信息
        f.write("Branch Coverage Improvements:\n")
        f.write(f"Number of contracts with improvements: {len(branch_improvements)}\n")
        f.write(f"Percentage of total: {(len(branch_improvements) / len(df)) * 100:.2f}%\n\n")
        f.write("All Branch Coverage Improvements:\n")
        f.write(branch_improvements[['Contract Path', 
                                   'Branch Coverage (baseline)',
                                   'Branch Coverage (llm-mutate)',
                                   'Improvement']].to_string())
        f.write("\n\n")
        
        # Code Coverage 详细信息
        f.write("Code Coverage Improvements:\n")
        f.write(f"Number of contracts with improvements: {len(code_improvements)}\n")
        f.write(f"Percentage of total: {(len(code_improvements) / len(df)) * 100:.2f}%\n\n")
        f.write("All Code Coverage Improvements:\n")
        f.write(code_improvements[['Contract Path', 
                                 'Code Coverage (baseline)',
                                 'Code Coverage (llm-mutate)',
                                 'Improvement']].to_string())
        
    # 将改进的合约信息保存为CSV
    branch_improvements.to_csv(f'{output_dir}/branch_improvements.csv', index=False)
    code_improvements.to_csv(f'{output_dir}/code_improvements.csv', index=False)
    
    # === 新增: 创建并保存合并后的改进信息 ===
    # 1. 获取所有改进的合约路径
    improved_contracts = pd.concat([
        branch_improvements['Contract Path'],
        code_improvements['Contract Path']
    ]).unique()
    
    # 2. 创建合并数据框
    merged_improvements = pd.DataFrame()
    for contract in improved_contracts:
        branch_data = branch_improvements[branch_improvements['Contract Path'] == contract]
        code_data = code_improvements[code_improvements['Contract Path'] == contract]
        
        row_data = {
            'Contract Path': contract,
            'Branch Coverage (baseline)': branch_data['Branch Coverage (baseline)'].iloc[0] if not branch_data.empty else None,
            'Branch Coverage (llm-mutate)': branch_data['Branch Coverage (llm-mutate)'].iloc[0] if not branch_data.empty else None,
            'Branch Coverage Improvement': branch_data['Improvement'].iloc[0] if not branch_data.empty else None,
            'Code Coverage (baseline)': code_data['Code Coverage (baseline)'].iloc[0] if not code_data.empty else None,
            'Code Coverage (llm-mutate)': code_data['Code Coverage (llm-mutate)'].iloc[0] if not code_data.empty else None,
            'Code Coverage Improvement': code_data['Improvement'].iloc[0] if not code_data.empty else None,
            'Execution Time (baseline)': df[df['Contract Path'] == contract]['Execution Time (baseline)'].iloc[0],
            'Execution Time (llm-mutate)': df[df['Contract Path'] == contract]['Execution Time (llm-mutate)'].iloc[0]
        }
        merged_improvements = pd.concat([merged_improvements, pd.DataFrame([row_data])], ignore_index=True)
    
    # 按照分支覆盖率和代码覆盖率的改进幅度排序
    merged_improvements['Sort Score'] = (
        merged_improvements['Branch Coverage Improvement'].fillna(0) + 
        merged_improvements['Code Coverage Improvement'].fillna(0)
    )
    merged_improvements = merged_improvements.sort_values('Sort Score', ascending=False)
    
    # 删除排序用的列，并且不包含 Total Improvement
    merged_improvements = merged_improvements.drop(columns=['Sort Score'])
    
    # 4. 保存合并后的 CSV
    merged_improvements.to_csv(f'{output_dir}/all_improvements.csv', index=False)
    
    # 保存改进合约路径列表
    with open(f'{output_dir}/improved_contract_paths.txt', 'w') as f:
        for contract in improved_contracts:
            f.write(f"{contract}\n")
            
    # 更新分析结果文本文件，添加合并信息
    with open(f'{output_dir}/improvement_analysis.txt', 'a') as f:
        f.write("\n\nMerged Improvements Summary:\n")
        f.write(f"Total unique contracts with improvements: {len(improved_contracts)}\n")
        f.write("See 'all_improvements.csv' for detailed merged results\n")
    
    return {
        'total_analyzed': len(df),
        'branch_improvements': {
            'count': len(branch_improvements),
            'percentage': (len(branch_improvements) / len(df)) * 100,
            'contracts': branch_improvements['Contract Path'].tolist()
        },
        'code_improvements': {
            'count': len(code_improvements),
            'percentage': (len(code_improvements) / len(df)) * 100,
            'contracts': code_improvements['Contract Path'].tolist()
        },
        'total_improved_contracts': len(improved_contracts)
    }

if __name__ == "__main__":
    results = analyze_and_extract_improvements()
    print("\n📊 分析结果:")
    print(f"分析的合约总数: {results['total_analyzed']}")
    print(f"分支覆盖率改进的合约: {results['branch_improvements']['count']} ({results['branch_improvements']['percentage']:.2f}%)")
    print(f"代码覆盖率改进的合约: {results['code_improvements']['count']} ({results['code_improvements']['percentage']:.2f}%)")
    print(f"总的改进合约数: {results['total_improved_contracts']}")
    print("\n💾 结果已保存在 comparison_reports/improved_contracts/")