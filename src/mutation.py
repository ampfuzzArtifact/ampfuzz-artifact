#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' Mutation implementation. '''

import random
import os
import json
import datetime

from utils import settings
from utils.utils import get_interface_from_abi

from ...plugin_interfaces.operators.mutation import Mutation
from .llm_mutator import LLMMutator

from web3 import Web3

class Mutation(Mutation):
    def __init__(self, pm, mode='baseline'):
        '''
        :param pm: The probability of mutation (usually between 0.001 ~ 0.1)
        :type pm: float in (0.0, 1.0]
        '''
        if pm <= 0.0 or pm > 1.0:
            raise ValueError('Invalid mutation probability')

        self.pm = pm
        self.mode = mode  # 添加模式控制
        self.llm_mutator = None
        self._llm_mutation_strategy = None 
        self._strategy_generation = -1 # 记录策略是为哪一代生成的，避免使用过时的策略
        self.contract_abi = None 

        self.function_info_map = None # 第三次实验pool添加

        # self.mutation_config = {
        #     'bit_flip_ratio': 0.8,  # 比特翻转概率
        #     'max_mutations': 5,      # 最大变异次数
        #     'boundary_values': [0, 1, -1, 2**256-1] # 边界值列表
        # }


    def _initialize_llm_helper(self, engine):
        if self.llm_mutator is None:
            # self.contract_abi = get_interface_from_abi(engine.analysis[0].env.abi) # x 这是interface
            self.contract_abi = engine.analysis[0].env.abi
            self.llm_mutator = LLMMutator(
                abi=self.contract_abi,
                contract_source=engine.analysis[0].env.contract_source_code) 



    def mutate(self, individual, engine):
        # analysis后面肯定要处理，只能是execution_trace_analysis

        # 根据模式决定是否使用 LLM 变异
        use_llm_mutation = self.mode in ['llm-mutate', 'llm-full']

        if use_llm_mutation:
            self._initialize_llm_helper(engine)

            # 2. 检查是否有新覆盖的“英雄”个体信息
            #    并且检查当前代数，确保只在发现新覆盖的那一代请求一次LLM
            if hasattr(engine.analysis[0].env, 'llm_amplifier_context') and self._strategy_generation != engine.current_generation: # ?
                engine.logger.info("New coverage detected! Triggering LLM amplifier for mutation...")   
                    
                hero_info = engine.analysis[0].env.llm_amplifier_context
                
                # 假设合约源码在env中 # contract_source = engine.analysis[0].env.contract_source_code # 8-19 源码不好搞，决定改为abi

                self._llm_mutation_strategy = self.llm_mutator.get_mutation_strategy(
                    hero_info.get("logs", "No logs available"), 
                    hero_info.get("test_case_str", ""),
                    hero_info.get("order", "Unknown order")
                )

                self._strategy_generation = engine.current_generation
            elif not hasattr(engine.analysis[0].env, 'llm_amplifier_context'):
                # 如果没有新覆盖，就清除旧策略
                self._llm_mutation_strategy = None

        # 完善数据结构：在变异逻辑的最开始，确保映射已经构建
        if self.function_info_map is None:
            # 假设 individual.generator 拥有 abi 属性
            self.function_info_map = self._build_function_info_map(individual.generator.abi)


        # 3. 执行变异，根据是否存在LLM策略来决定方式
        if use_llm_mutation and self._llm_mutation_strategy: # and random.random() < self.pm:
            return self.llm_guided_mutation(individual, self._llm_mutation_strategy)

        else:
            for gene in individual.chromosome:
                # TRANSACTION
                function_hash = gene["arguments"][0]
                for element in gene:
                    if element != "account" and element != "amount" and element != "gaslimit":
                        for argument_index in range(1, len(gene["arguments"])):
                            if random.random() > self.pm:
                                continue
                            argument_type = individual.generator.interface[function_hash][argument_index - 1]
                            argument = individual.generator.get_random_argument(argument_type,
                                                                                function_hash,
                                                                                argument_index - 1)
                            gene["arguments"][argument_index] = argument

                self.get_else_mutation_info(individual=individual, gene=gene)

            individual.solution = individual.decode()
            return individual


    def get_else_mutation_info(self, individual, gene):
        # for gene in individual.chromosome:
        #     # TRANSACTION
        #     function_hash = gene["arguments"][0]
        #     for element in gene:
        #         if element == "account" and random.random() <= self.pm:
        #             gene["account"] = individual.generator.get_random_account(function_hash)
        #         elif element == "amount" and random.random() <= self.pm:
        #             gene["amount"] = individual.generator.get_random_amount(function_hash)
        #         elif element == "gaslimit" and random.random() <= self.pm:
        #             gene["gaslimit"] = individual.generator.get_random_gaslimit(function_hash)
        #         else:
        #             for argument_index in range(1, len(gene["arguments"])):
        #                 if random.random() > self.pm:
        #                     continue
        #                 argument_type = individual.generator.interface[function_hash][argument_index - 1]
        #                 argument = individual.generator.get_random_argument(argument_type,
        #                                                                     function_hash,
        #                                                                     argument_index - 1)
        #                 gene["arguments"][argument_index] = argument
        
        # 除arguments外其他所有参数
        function_hash = gene["arguments"][0]
        if "account" in gene and random.random() <= self.pm:
            gene["account"] = individual.generator.get_random_account(function_hash)
        elif "amount" in gene and random.random() <= self.pm:
            gene["amount"] = individual.generator.get_random_amount(function_hash)
        elif "gaslimit" in gene and random.random() <= self.pm:
            gene["gaslimit"] = individual.generator.get_random_gaslimit(function_hash)

        # BLOCK
        if "timestamp" in gene:
            if random.random() <= self.pm:
                gene["timestamp"] = individual.generator.get_random_timestamp(function_hash)
        else:
            gene["timestamp"] = individual.generator.get_random_timestamp(function_hash)

        if "blocknumber" in gene:
            if random.random() <= self.pm:
                gene["blocknumber"] = individual.generator.get_random_blocknumber(function_hash)
        else:
            gene["blocknumber"] = individual.generator.get_random_blocknumber(function_hash)

        # GLOBAL STATE
        if "balance" in gene:
            if random.random() <= self.pm:
                gene["balance"] = individual.generator.get_random_balance(function_hash)
        else:
            gene["balance"] = individual.generator.get_random_balance(function_hash)

        if "call_return" in gene:
            for address in gene["call_return"]:
                if random.random() <= self.pm:
                    gene["call_return"][address] = individual.generator.get_random_callresult(function_hash, address)
        else:
            gene["call_return"] = dict()
            address, call_return_value = individual.generator.get_random_callresult_and_address(function_hash)
            if address and address not in gene["call_return"]:
                gene["call_return"][address] = call_return_value

        if "extcodesize" in gene:
            for address in gene["extcodesize"]:
                if random.random() <= self.pm:
                    gene["extcodesize"][address] = individual.generator.get_random_extcodesize(function_hash, address)
        else:
            gene["extcodesize"] = dict()
            address, extcodesize_value = individual.generator.get_random_extcodesize_and_address(function_hash)
            if address and address not in gene["extcodesize"]:
                gene["extcodesize"][address] = extcodesize_value

        if "returndatasize" in gene:
            for address in gene["returndatasize"]:
                if random.random() <= self.pm:
                    gene["returndatasize"][address] = individual.generator.get_random_returndatasize(function_hash, address)
        else:
            gene["returndatasize"] = dict()
            address, returndatasize_value = individual.generator.get_random_returndatasize_and_address(function_hash)
            if address and address not in gene["returndatasize"]:
                gene["returndatasize"][address] = returndatasize_value

        # individual.solution = individual.decode()
        # return individual


    def llm_guided_mutation(self, individual, llm_targets):
        """
        一个新的、由LLM指导的混合变异函数。
        - individual: Confuzzius 中的个体，包含 chromosome 和 generator。
        - llm_targets: 从LLM获取的变异目标。
        """
        
        # 定义两种变异概率
        high_priority_pm = 0.8  # LLM 目标的变异概率
        background_pm = self.pm # Confuzzius 原有的背景变异概率

        # 遍历测试用例中的每一笔交易 (gene)
        for gene in individual.chromosome:
            function_hash = gene["arguments"][0]
            # 从 hash 获取函数名和参数名列表 (这需要一个辅助函数)
            # 从预先构建的映射中安全地查找函数信息，不再有任何假设
            if function_hash not in self.function_info_map:
                # 如果哈希不在映射中（可能是内部调用或未知函数），则跳过对该gene的LLM指导
                continue

            
            func_info = self.function_info_map[function_hash]
            func_name = func_info["name"]
            param_names = func_info["params"]

            # 检查当前函数是否是 LLM 的目标
            is_targeted_function = func_name in llm_targets
            targeted_params = llm_targets.get(func_name, [])

            # --- 1. 变异交易参数 (Arguments) ---
            for i in range(1, len(gene["arguments"])):
                param_index = i - 1
                # 确保不会因参数数量不匹配而出错
                if param_index >= len(param_names):
                    break 
                
                param_name = param_names[param_index]
                
                # 决定使用哪个概率
                current_pm = high_priority_pm if is_targeted_function and param_name in targeted_params else background_pm
                
                if random.random() <= current_pm:
                    if is_targeted_function and param_name in targeted_params:
                        print(f"  [LLM-GUIDED] Mutating targeted parameter '{param_name}' in function '{func_name}'")
                    
                    # **核心：复用 Confuzzius 的 generator！**
                    argument_type = individual.generator.interface[function_hash][param_index]
                    new_argument = individual.generator.get_random_argument(argument_type,
                                                                            function_hash,
                                                                            param_index)
                    gene["arguments"][i] = new_argument


            self.get_else_mutation_info(individual=individual, gene=gene)

        individual.solution = individual.decode()
        return individual


    def _build_function_info_map(self, abi):
        """
        遍历 self.abi 构建一个从 function_hash 到函数详细信息的映射。
        这是在变异前必须运行的关键准备步骤。
        
        返回的映射结构:
        {
            '0xa9059cbb': {'name': 'transfer', 'params': ['_to', '_value']},
            '0x095ea7b3': {'name': 'approve', 'params': ['_spender', '_value']}
        }
        """
        function_info_map = {}

        for entry in abi:
            # 我们只关心类型为 'function' 的条目
            if entry.get('type') == 'function':
                func_name = entry['name']
                
                # 提取参数类型和参数名
                input_types = [inp['type'] for inp in entry['inputs']]
                param_names = [inp['name'] for inp in entry['inputs']]
                
                # 构建函数签名，例如 "transfer(address,uint256)"
                signature_text = f"{func_name}({','.join(input_types)})"
                
                # 计算标准的4字节函数选择器 (hash)
                # Web3.keccak(text=...) 是计算Keccak-256哈希的标准方法
                # [:10] 获取 '0x' 加上前4个字节 (8个十六进制字符)
                # func_hash = Web3.keccak(text=signature_text).hex()[:10]
                # func_hash = Web3.keccak(text=signature_text.encode("utf-8")).hex()[:10]
                w3 = Web3()
                func_hash = w3.sha3(text=signature_text).hex()[2:10]

                normalized_func_hash = f"0x{func_hash}" if not func_hash.startswith("0x") else func_hash
                
                # 存储到映射中
                function_info_map[normalized_func_hash] = {
                    "name": func_name,
                    "params": param_names
                }
                
        return function_info_map