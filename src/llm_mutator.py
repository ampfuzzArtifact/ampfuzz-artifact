import json
import os
from openai import OpenAI
from Levenshtein import distance as levenshtein_distance
from dotenv import load_dotenv
from typing import Dict, Tuple, Any

load_dotenv()
API_KEY = os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL")

class LLMMutator:
    def __init__(self, abi, contract_source=""):
        self.abi = abi
        self.contract_source = contract_source
        self.state_functions = self._extract_state_functions()
        self.remind_history = ""
        self.max_edit_distance = 2

        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    # prompt里用到
    def _extract_state_functions(self):
        """提取状态变更函数的信息，格式化为 'index:function_signature' 形式
        Returns:
            str: 格式化后的函数签名字符串, 如 "1:deposit(uint256 amount),2:withdraw(uint256 value)"
        """
        functions = []
        index = 1

        # 处理普通函数
        for func in self.abi:
            if func['type'] == 'function' and not func['constant']:
                # 构建参数列表，格式为 "type name"
                params = []
                for inp in func['inputs']:
                    param_str = f"{inp['type']} {inp['name']}"
                    params.append(param_str)
                
                # 构建完整的函数签名
                signature = f"{index}:{func['name']}({','.join(params)})"
                functions.append(signature)
                index += 1
        
        # 处理构造函数
        for func in self.abi:
            if func['type'] == 'constructor':
                params = []
                for inp in func['inputs']:
                    param_str = f"{inp['type']} {inp['name']}"
                    params.append(param_str)
                
                signature = f"{index}:constructor({','.join(params)})"
                functions.append(signature)
                break  # 只处理一个构造函数

        return ",".join(functions)

    def _clean_json_string(self, response_str: str) -> str:
        """清理 LLM 响应中的 JSON 字符串"""
        if response_str.startswith("```json"):
            response_str = response_str[7:]
        if response_str.endswith("```"):
            response_str = response_str[:-3]
        
        response_str = response_str.strip()
        # 替换可能存在的单引号
        response_str = response_str.replace("'", '"')
        return response_str

    def _calculate_edit_distance(self, s1, s2):
        """计算两个字符串之间的莱文斯坦编辑距离"""
        return levenshtein_distance(s1, s2)

    def _validate_and_parse_feedback(self, feedback_str):
        """
        一个为新Prompt设计的验证函数。
        验证 LLM 的反馈格式为 {'func_name': ['param1', 'param2', ...]}.
        """
        remind_message = ""
        
        # 1. 验证是否是合法的JSON (这部分逻辑保持不变)
        try:
            start_pos = feedback_str.find('{')
            end_pos = feedback_str.rfind('}') + 1
            if start_pos == -1 or end_pos == 0:
                return False, None, "The feedback did not contain a valid JSON object. "
            
            json_str = feedback_str[start_pos:end_pos]
            llm_feedback = json.loads(json_str)
        except json.JSONDecodeError:
            return False, None, "The feedback was not in a valid JSON format. "

        if not isinstance(llm_feedback, dict) or not llm_feedback:
            return False, None, "The JSON object is empty or invalid. Please provide suggestions for all functions. "

        validated_strategy = {}
        
        # 2. 遍历合约中定义的所有函数 (ground truth)
        for func_name_from_contract, params_from_contract in self.state_functions.items():
            
            # 容错匹配：在LLM的反馈中查找函数名
            matched_func_name_from_llm = None
            for func_name_from_llm in llm_feedback.keys():
                if self._calculate_edit_distance(func_name_from_contract, func_name_from_llm) <= self.max_edit_distance:
                    matched_func_name_from_llm = func_name_from_llm
                    break
            
            # 检查点 A: 确保每个函数都在LLM的反馈中
            if not matched_func_name_from_llm:
                remind_message += f"The function '{func_name_from_contract}' is missing from your JSON response. "
                continue

            llm_param_list = llm_feedback[matched_func_name_from_llm]

            # 检查点 B: 确保值是一个列表
            if not isinstance(llm_param_list, list):
                remind_message += f"For function '{func_name_from_contract}', the value must be a list of parameter names, but I received a {type(llm_param_list)}. "
                continue

            validated_param_list = []
            # 3. 遍历LLM建议的参数列表
            for param_name_from_llm in llm_param_list:
                
                # 容错匹配：在合约的真实参数列表中查找LLM建议的参数
                matched_param_name_from_contract = None
                for p_name_from_contract in params_from_contract:
                    if self._calculate_edit_distance(param_name_from_llm, p_name_from_contract) <= self.max_edit_distance:
                        matched_param_name_from_contract = p_name_from_contract
                        break

                # 检查点 C: 确保LLM建议的每个参数都真实存在
                if matched_param_name_from_contract:
                    # 使用合约中标准的名字进行存储，以纠正LLM可能的微小拼写错误
                    validated_param_list.append(matched_param_name_from_contract)
                else:
                    remind_message += f"In function '{func_name_from_contract}', you suggested mutating a parameter named '{param_name_from_llm}', but this parameter does not exist. The available parameters are: {params_from_contract}. "

            # 存储经过验证和清理的策略
            validated_strategy[func_name_from_contract] = validated_param_list

        # 如果在整个验证过程中收集到了任何错误信息，则验证失败
        if remind_message:
            return False, None, remind_message
        
        # 最后的完整性检查，确保所有函数都被成功处理
        if len(validated_strategy) != len(self.state_functions):
            return False, None, "Some functions were missing from the final validated strategy. Please regenerate the full list."

        # 所有检查通过，返回成功
        return True, validated_strategy, ""


    def get_mutation_strategy(self, logs, test_case_str, execution_order_str, max_retries=3):
        is_valid = False
        mutation_info = {}
        remind = "" 
        
        for _ in range(max_retries):            
            prompt = f"""I am conducting fuzz testing on a smart contract and need suggestions on which parameters of multiple state functions should be mutated based on execution logs.

            The logs from a recent contract execution are: {logs}.
            The functions within the contract were executed in the following order: {execution_order_str}.
            The current test case that was used to trigger this execution sequence is as follows: {test_case_str}.
            The smart contract is as follows: 
            {self.contract_source}

            Please use the exact parameter names from the following state functions to provide mutation suggestions.
            State functions and their parameters are as follows: {self.state_functions}.
    
            Based on the analysis of the execution trace and contract logic, please identify the function parameters that are the **most promising targets for mutation** to discover new behaviors or vulnerabilities.

            Your result should be a JSON object where the key is the function name and the value is a list of parameter names that should be prioritized for mutation.

            Example format:
            {{
                "transfer": ["amount"],
                "approve": ["spender", "amount"],
                "withdraw": [] 
            }}

            Only list the parameters that you have a high confidence will be impactful. If no parameters in a function are promising, provide an empty list.
            """


            
            # **关键部分**：如果不是第一次尝试，就向LLM提供具体的修正指令
            if remind:
                prompt += f"\nIMPORTANT: Your previous response had errors. Please correct them. Here are the issues I found: {remind}"
    
            try:
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", 
                         "content": "You are a smart contract analysis expert." + 
                         " Your goal is to propose changes to the test case parameters that are likely to alter the control flow seen in the execution trace (e.g., make a JUMPI branch go the other way)." + 
                         " You must provide your response in the requested JSON format."},

                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.8,
                    response_format={"type": "json_object"} 
                )
                content = response.choices[0].message.content

                return json.loads(content)
                
                # 3. 验证并解析反馈
                is_valid, mutation_info, error_message = self._validate_and_parse_feedback(content)
                
                if is_valid:
                    print("Successfully received a valid mutation strategy!")
                    return mutation_info # 成功，直接返回结果
                else:
                    remind = error_message # 验证失败，更新提醒信息以备下次循环使用
            
            except Exception as e:
                print(f"An error occurred during LLM request or validation: {e}")
                remind = f"An exception occurred: {e}. Please ensure the output is a single, valid JSON object. "
        
        print("Failed to get a valid mutation strategy after all retries.")
        return {} # 如果所有尝试都失败了，返回空字典
    
    