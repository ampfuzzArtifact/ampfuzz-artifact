import json
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv
from utils.utils import *
import json

import time
from string import Template
from collections import defaultdict  # 新增

load_dotenv(find_dotenv())
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

class LLMGenerator:
    def __init__(self, generator):
        self.generator = generator
        self.interface = generator.interface
        self.abi = generator.abi
        self.client = client
        self.logger = initialize_logger("LLMGenerator")
        self.prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")

        # 统计器
        self.token_usage = {"prompt": 0, "completion": 0, "total": 0}
        self.usage_by_phase = defaultdict(lambda: {"prompt": 0, "completion": 0, "total": 0})
        # JSONL 日志文件（统一写到 experiments_results 下）
        self._usage_log = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "../../../experiments_results/llm_usage.jsonl")
        )
        
        # === 过滤统计器 (Filter Statistics) ===
        self.filter_stats = {
            "total_generated": 0,       # LLM 生成的总种子数
            "total_accepted": 0,        # 通过验证的种子数
            "total_rejected": 0,        # 被拒绝的种子数
            "rejection_reasons": {
                "invalid_format": 0,       # 格式错误（arguments不是列表等）
                "abi_mismatch": 0,         # 函数名不在 ABI 中
                "type_sanitize_fail": 0,   # 参数类型清洗失败
                "arg_count_mismatch": 0,   # 参数数量不匹配
                "json_parse_fail": 0       # JSON 解析失败
            }
        }
        self._filter_log = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "../../../experiments_results/filter_stats.jsonl")
        )

        # === 构建函数名到哈希的映射 (Function Name to Hash Mapping) ===
        # interface 的结构是 {hash: [input_types], "constructor": [...], "fallback": []}
        # 我们需要从 ABI 中提取函数名和参数类型，构建反向映射
        self.function_name_to_hash = {}  # {"transfer": "0x12345678", ...}
        self.function_info = {}  # {"transfer": {"hash": "0x...", "inputs": [...]}, ...}
        self._build_function_mappings()

        # 从合约路径中提取相对路径信息
        contract_path = self.generator.contract
        if isinstance(contract_path, str) and contract_path.startswith("dataset/"):
            self.contract_relative_path = contract_path
        else:
            self.contract_relative_path = None


    """
    调用_build_prompt() 执行llm
    """
    def generate_with_llm(self, mode, num_cases=5, phase="init", temperature=None): # 添加了phase和temperature两个参数
        dependency_json_str = "{}"  # 默认空依赖
# if self.contract_relative_path:
        #     # 将合约路径转换为对应的依赖文件路径
        #     deps_path = self.contract_relative_path.replace("dataset/", "scripts/slither_outputs/")
        #     deps_path = deps_path.replace(".sol", "_deps.json")
            
        #     self.logger.debug(f"Looking for dependencies at: {deps_path}")
            
        #     if os.path.exists(deps_path):
        #         with open(deps_path) as f:
        #             dependency_json_str = f.read()
        #         self.logger.info(f"Loaded dependencies from {deps_path}")
        #     else:
        #         self.logger.warning(f"No dependency file found at {deps_path}")
        # prompt = self._build_prompt_RAW(num_cases, dependency_json_str)

        if mode == 'llm-cot' or 'llm-full':
            prompt = self._build_cot_prompt(num_cases)
        elif mode == 'llm':
            prompt = self._build_basic_prompt(num_cases)
        elif mode == 'new-llm':  # 添加新的模式
            prompt = self._build_new_prompt(num_cases)
        else:
            self.logger.warning(f"未知模式: {mode}, 回退 basic")
            prompt = self._build_basic_prompt(num_cases)

        # 默认温度：初始化阶段更探索，变异阶段更稳定
        if temperature is None:
            temperature = 0.8 if phase == "init" else 0.5

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            # 记录 token usage
            usage = getattr(response, "usage", None)
            if usage:
                p = getattr(usage, "prompt_tokens", 0)
                c = getattr(usage, "completion_tokens", 0)
                t = getattr(usage, "total_tokens", p + c)
                self.token_usage["prompt"] += p
                self.token_usage["completion"] += c
                self.token_usage["total"] += t
                self.usage_by_phase[phase]["prompt"] += p
                self.usage_by_phase[phase]["completion"] += c
                self.usage_by_phase[phase]["total"] += t
                # 逐条写 JSONL，便于后处理
                os.makedirs(os.path.dirname(self._usage_log), exist_ok=True)
                with open(self._usage_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "contract": self.generator.contract,
                        "phase": phase,
                        "mode": mode,
                        "model": "deepseek-chat",
                        "temperature": temperature,
                        "prompt_tokens": p,
                        "completion_tokens": c,
                        "total_tokens": t
                    }, ensure_ascii=False) + "\n")

            content = response.choices[0].message.content
            res = self._parse_and_validate_response(content)
            return res
        except Exception as e:
            print(f"LLM调用失败: {e}")
            return []

    def export_token_usage(self, path=None):
        # 导出本轮累计（可在主流程每个合约结束后调用）
        if path is None:
            path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "../../../experiments_results/llm_usage_summary_run.json")
            )
        payload = {
            "contract": self.generator.contract,
            "total": self.token_usage,
            "by_phase": self.usage_by_phase
        }
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Token 使用统计已写入 {path}")
        except Exception as e:
            self.logger.error(f"写入 token 使用统计失败: {e}")

    def export_filter_stats(self):
        """导出过滤统计到 JSONL 文件"""
        if self.filter_stats["total_generated"] == 0:
            return  # 没有生成任何种子，跳过
        
        # 计算过滤率
        total_gen = self.filter_stats["total_generated"]
        total_rej = self.filter_stats["total_rejected"]
        filter_rate = (total_rej / total_gen * 100) if total_gen > 0 else 0.0
        
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "contract": self.generator.contract,
            "total_generated": total_gen,
            "total_accepted": self.filter_stats["total_accepted"],
            "total_rejected": total_rej,
            "filter_rate_percent": round(filter_rate, 2),
            "rejection_reasons": self.filter_stats["rejection_reasons"].copy()
        }
        
        try:
            os.makedirs(os.path.dirname(self._filter_log), exist_ok=True)
            with open(self._filter_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.logger.info(f"Filter stats exported: {total_rej}/{total_gen} rejected ({filter_rate:.1f}%)")
        except Exception as e:
            self.logger.error(f"Failed to export filter stats: {e}")

    def reset_filter_stats(self):
        """重置过滤统计（每个合约开始时调用）"""
        self.filter_stats = {
            "total_generated": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "rejection_reasons": {
                "invalid_format": 0,
                "abi_mismatch": 0,
                "type_sanitize_fail": 0,
                "arg_count_mismatch": 0,
                "json_parse_fail": 0
            }
        }

    def _build_function_mappings(self):
        """从 ABI 构建函数名到哈希值的映射"""
        from web3 import Web3
        
        if not self.abi:
            return
        
        for field in self.abi:
            if field.get('type') == 'function':
                func_name = field['name']
                inputs = field.get('inputs', [])
                
                # 构建函数签名
                signature = func_name + '('
                input_types = []
                for i, inp in enumerate(inputs):
                    input_type = inp['type']
                    input_types.append(input_type)
                    signature += input_type
                    if i < len(inputs) - 1:
                        signature += ','
                signature += ')'
                
                # 计算函数选择器 (4字节哈希) - 使用 sha3 代替 keccak
                func_hash = Web3.sha3(text=signature)[0:4].hex()
                
                self.function_name_to_hash[func_name] = func_hash
                self.function_info[func_name] = {
                    "hash": func_hash,
                    "signature": signature,
                    "inputs": input_types
                }
        
        # 添加特殊函数
        if 'constructor' in self.interface:
            self.function_name_to_hash['constructor'] = 'constructor'
        if 'fallback' in self.interface:
            self.function_name_to_hash['fallback'] = 'fallback'
        
        self.logger.debug(f"Built function mappings: {list(self.function_name_to_hash.keys())}")

    """
    构造prompt
    """
    def _build_basic_prompt(self, num_cases):
        prompt = self._load_prompt_template("basic_prompt.txt")
        return prompt.format(
            num_cases=num_cases,
            contract=self.generator.contract,
            abi=self.abi
        )

    def _build_cot_prompt(self, num_cases):
        prompt = self._load_prompt_template("cot_better_prompt.txt") # cot_prompt.txt
        return prompt.format(
            num_cases=num_cases,
            contract=self.generator.contract,
            abi=self.abi # add raw
        )

    def _build_new_prompt(self, num_cases):
        """构建新的 prompt 模板"""
        prompt = self._load_prompt_template("new_idea_prompt.txt")
        current_time = int(time.time())

        template = Template(prompt)
        return template.substitute(
            num_cases=num_cases,
            contract=self.generator.contract,
            abi=self.generator.abi,
            current_time=current_time
        )
    
    def _build_prompt_RAW(self, num_cases, dependency_json_str):
        prompt = self._load_prompt_template("raw_prompt.txt")
        return prompt.format(
            num_cases=num_cases,
            contract=self.generator.contract,
            abi=self.generator.abi,
            dependency_json_str=dependency_json_str
        )
    
    """
    读取prompt文件
    """
    def _load_prompt_template(self, prompt_name):
        prompt_path = os.path.join(self.prompt_dir, prompt_name)
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(
                f"Prompt template '{prompt_name}' not found at {prompt_path}. "
                f"Available templates: {os.listdir(self.prompt_dir)}"
            )
        try:
            with open(prompt_path, 'r') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"Failed to read prompt template '{prompt_name}': {str(e)}")
            raise

    """
    验证格式
    """        
    def _parse_and_validate_response(self, text):    
        try:
            data = json.loads(text.strip())
            cases = data.get("transactions", [])
            
            # 记录本次 LLM 生成的总数
            batch_total = len(cases)
            self.filter_stats["total_generated"] += batch_total
            
            valid_cases = []
            for case in cases:
                # 1: 基础验证
                if not isinstance(case.get("arguments", []), list) or not case["arguments"]:
                    self.logger.warning("Invalid case format: 'arguments' must be a non-empty list.")
                    self.filter_stats["rejection_reasons"]["invalid_format"] += 1
                    self.filter_stats["total_rejected"] += 1
                    continue
                
                function_identifier = case["arguments"][0]
                
                # 2: 将函数名转换为哈希值（如果需要）
                # LLM 可能返回 "transfer" 或 "0xa9059cbb"，我们需要统一处理
                if function_identifier in self.function_name_to_hash:
                    # LLM 返回的是函数名，转换为哈希
                    function_hash = self.function_name_to_hash[function_identifier]
                    function_name = function_identifier
                elif function_identifier in self.interface:
                    # LLM 返回的已经是哈希值或特殊标识符
                    function_hash = function_identifier
                    # 尝试找回函数名（用于日志）
                    function_name = next((name for name, h in self.function_name_to_hash.items() if h == function_identifier), function_identifier)
                else:
                    self.logger.warning(f"Invalid function identifier in LLM response: {function_identifier}. Available functions: {list(self.function_name_to_hash.keys())}")
                    self.filter_stats["rejection_reasons"]["abi_mismatch"] += 1
                    self.filter_stats["total_rejected"] += 1
                    continue
                
                # 更新 arguments[0] 为哈希值（符合 Confuzzius 内部格式）
                case["arguments"][0] = function_hash
                
                # 2: 参数类型清洗 (核心修复逻辑)
                try:
                    self._sanitize_argument_types(case)
                except ValueError as ve:
                    # 参数数量不匹配
                    if "Argument count mismatch" in str(ve):
                        self.filter_stats["rejection_reasons"]["arg_count_mismatch"] += 1
                    else:
                        self.filter_stats["rejection_reasons"]["type_sanitize_fail"] += 1
                    self.filter_stats["total_rejected"] += 1
                    self.logger.error(f"Failed to sanitize arguments for function '{function_name}': {ve}. Skipping case.")
                    continue
                except Exception as e:
                    self.filter_stats["rejection_reasons"]["type_sanitize_fail"] += 1
                    self.filter_stats["total_rejected"] += 1
                    self.logger.error(f"Failed to sanitize arguments for function '{function_name}': {e}. Skipping case.")
                    continue
                
                # 3: 构建 Confuzzius 最终需要的字典
                valid_case = {
                    "arguments": case["arguments"],
                    "amount": int(case.get("amount", 0)),
                    "blocknumber": int(case.get("blocknumber", 1)),
                    "timestamp": int(case.get("timestamp", 0)),
                    # "gaslimit": case.get("gaslimit", self.generator.get_random_gaslimit(function_name)),  2025.8.11 modified
                    "call_return": {},
                    "extcodesize": {},
                    "returndatasize": {}
                }
                valid_cases.append(valid_case)
                self.filter_stats["total_accepted"] += 1
            
            self.logger.info(f"Generated {len(valid_cases)} valid test cases after sanitization. (Rejected: {batch_total - len(valid_cases)}/{batch_total})")
            return valid_cases
        except json.JSONDecodeError as e:
            self.filter_stats["rejection_reasons"]["json_parse_fail"] += 1
            self.logger.error(f"LLM response JSON parsing failed: {e}\nRaw content:\n{text}")
            return []
        except Exception as e:
            self.logger.error(f"LLM response parsing failed: {e}\nRaw content:\n{text}")
            return []

    def _sanitize_argument_types(self, case):
        arguments = case["arguments"]
        function_hash = arguments[0]  # 此时已经是哈希值

        # 步骤 A: 从 interface 中获取参数类型列表
        # interface 的结构是 {hash: [input_types], "constructor": [...], "fallback": []}
        if function_hash not in self.interface:
            raise ValueError(f"Function hash '{function_hash}' not found in fuzzer's interface.")

        # 获取预期的参数类型列表
        expected_types = self.interface[function_hash]
        
        # 找回函数名用于日志（但保持 arguments[0] 为哈希值以兼容 Confuzzius 内部格式）
        function_name = next((name for name, h in self.function_name_to_hash.items() if h == function_hash), function_hash)
        # 注意：不修改 arguments[0]，保持为哈希值！
        
        # 步骤 B: 使用获取到的类型信息进行清洗
        llm_args = arguments[1:]
        if len(expected_types) != len(llm_args):
            raise ValueError(f"Argument count mismatch for '{function_name}'. Expected {len(expected_types)}, got {len(llm_args)}.")

        for i, expected_type in enumerate(expected_types):
            param_index_in_list = i + 1
            actual_value = arguments[param_index_in_list]

            if 'uint' in expected_type or 'int' in expected_type:
                if isinstance(actual_value, str):
                    if actual_value.startswith('0x'):
                        arguments[param_index_in_list] = int(actual_value, 16)
                    else:
                        arguments[param_index_in_list] = int(actual_value)
                elif isinstance(actual_value, (int, float)):
                    arguments[param_index_in_list] = int(actual_value)
            
            elif 'bool' in expected_type:
                 if isinstance(actual_value, str):
                     arguments[param_index_in_list] = actual_value.lower() == 'true'


    # def save_cases_to_file(self, cases, output_dir="llm_cases"):    
    #     os.makedirs(output_dir, exist_ok=True)
    #     filename = f"{output_dir}/cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    #     with open(filename, 'w') as f:
    #         json.dump(cases, f, indent=2)
    
    # def save_prompt_to_file(self, prompt, output_dir="llm_prompts"): 
    #     os.makedirs(output_dir, exist_ok=True)
    #     filename = f"{output_dir}/prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    #     with open(filename, 'w') as f:
    #         f.write(prompt)
