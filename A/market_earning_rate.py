import numpy as np
from typing import List, Dict, Any, Literal

# 定义估值策略的类型别名
ValuationStrategy = Literal["basic", "dividend_correction", "pb_roe_squared", "roa_correction"]


class MarketEarningRatioValuator:
    """
    一个根据结构化逻辑体系，计算“市赚率（PR）”的工具类。

    该工具通过分析净资产收益率（ROE）的稳定性及其他财务指标，来自动选择正确的估值公式。
    其核心思想是量化沃伦·巴菲特的投资哲学——“以折扣价购买优质资产”。
    PR值约等于1.0被视为合理定价，低于1.0则可能表示资产存在折价。

    该类需要最新一年的核心财务指标，以及过去5年的ROE历史数据来进行策略决策。所有指标值
    （如ROA）应以数字形式提供（例如，15%应输入为15）。

    应用禁区（根据方法论）：
    - 避免用于依赖创新驱动价值的科技股（应使用PEG估值法）。
    - 避免用于处于衰退期的行业（应使用资产清算模型）。

    使用示例:
        # 最新一年的财务指标 (不包含ROE)
        latest_metrics = {
            'pe': 20.0,
            'pb': 4.4,
            'roa': 18.0,
            'dividend_payout_ratio': 0.30
        }
        # 过去5年的ROE历史数据 (最近的年份在前)
        roe_history = [22.0, 21.0, 24.0, 18.0, 19.0]

        # 1. 创建估值器实例
        evaluator = MarketEarningRatioValuator()

        # 2. 调用evaluate方法进行计算
        result = evaluator.evaluate(latest_metrics, roe_history)
        print(result)
        # 预期输出:
        # {
        #     'strategy': 'dividend_correction',
        #     'justification': 'ROE稳定，但分红率低于50%。应用N系数进行修正。',
        #     'pr_value': 1.5151515151515151,
        #     'inputs': {'pe': 20.0, 'roe': 22.0, 'dividend_payout_ratio': 0.3}
        # }
    """

    def __init__(self, roe_stability_threshold: float = 0.5):
        """
        初始化估值器。
        :param roe_stability_threshold: ROE稳定性的变异系数阈值，低于此值视为稳定。
        """
        self.roe_stability_threshold = roe_stability_threshold

    def _is_roe_stable(self, roe_history: List[float]) -> bool:
        """
        通过检查变异系数是否低于设定的阈值，来判断过去5年的ROE是否稳定。
        """
        # 处理平均ROE为零或接近零的情况
        mean_roe = np.mean(roe_history)
        if np.isclose(mean_roe, 0):
            return False

        coefficient_of_variation = np.std(roe_history) / mean_roe
        return coefficient_of_variation < self.roe_stability_threshold

    def _select_strategy(self, latest_data: Dict[str, Any], roe_history: List[float]) -> ValuationStrategy:
        """
        根据逻辑框架选择合适的估值策略。
        """
        roe = latest_data.get('roe')

        # 规则1：将ROE > 50%的情况作为特例，需要使用ROA进行修正。
        if roe is not None and roe > 50:
            return "roa_correction"

        # 规则2：根据ROE的稳定性进行区分。
        if self._is_roe_stable(roe_history):
            payout_ratio = latest_data.get('dividend_payout_ratio')
            # 对于稳定的ROE，检查分红率。
            if payout_ratio is not None and payout_ratio >= 0.5:
                return "basic"
            else:
                return "dividend_correction"
        else:
            # 对于不稳定的ROE（典型的周期股/困境股），使用PB-ROE²公式。
            return "pb_roe_squared"

    def evaluate(self, latest_metrics: Dict[str, Any], roe_history: List[float]) -> Dict[str, Any]:
        """
        通过选择策略并计算PR值，执行完整的估值。
        :param latest_metrics: 包含最新一年财务指标的字典（不应包含ROE）。
        :param roe_history: 包含过去5年ROE历史数据的列表，需按时间倒序排列（最近的在前）。
        :return: 一个包含所用策略、理由、计算结果和输入参数的字典。
        """
        if not isinstance(roe_history, list) or len(roe_history) < 4:
            raise ValueError("roe_history 需要一个包含至少5年ROE历史数据的列表。")
        if not isinstance(latest_metrics, dict):
            raise ValueError("latest_metrics 需要一个包含最新财务指标的字典。")

        # 将输入数据合并，以roe_history的第一个值为准
        latest_data = latest_metrics.copy()
        latest_data['roe'] = roe_history[0]  # 使用历史列表的第一个值作为当期ROE

        strategy = self._select_strategy(latest_data, roe_history)
        data = latest_data

        result = {
            "strategy": strategy,
            "justification": "",
            "pr_value": None,
            "inputs": {}
        }

        try:
            if strategy == "basic":
                result['justification'] = "ROE稳定且分红率高 (>=50%)。使用基础PR公式。"
                result['inputs'] = {'pe': data['pe'], 'roe': data['roe']}
                # 基础公式推导：PR = PE / ROE / 100，这里我们假设ROE单位为%，所以是 PE / ROE
                result['pr_value'] = data['pe'] / data['roe']

            elif strategy == "dividend_correction":
                result['justification'] = "ROE稳定，但分红率低于50%。应用N系数进行修正。"
                payout_ratio = data['dividend_payout_ratio']

                n_factor = 2.0  # 默认使用最大修正系数
                if payout_ratio and payout_ratio > 0:
                    n_factor = min(2.0, 0.5 / payout_ratio)
                    if n_factor < 1:
                        n_factor = 1

                basic_pr = data['pe'] / data['roe']
                result['inputs'] = {'pe': data['pe'], 'roe': data['roe'], 'dividend_payout_ratio': payout_ratio}
                result['pr_value'] = n_factor * basic_pr

            elif strategy == "pb_roe_squared":
                result['justification'] = "ROE不稳定（周期性/困境股模式）。使用PB-ROE²公式进行估值。"
                result['inputs'] = {'pb': data['pb'], 'roe': data['roe']}
                # 原始公式为 PR = PB / (ROE × ROE) / 100，这里ROE为百分比数字，所以是 PB * 100 / ROE²
                result['pr_value'] = (data['pb'] * 100) / (data['roe'] ** 2)

            elif strategy == "roa_correction":
                result['justification'] = "ROE > 50% 或杠杆异常。使用基于ROA的公式以消除杠杆失真。"
                # 1.5是用于估算去杠杆化ROE的经验系数。
                result['inputs'] = {'pe': data['pe'], 'roa': data['roa']}
                result['pr_value'] = data['pe'] / (1.5 * data['roa'])

        except KeyError as e:
            raise KeyError(f"策略 '{strategy}' 缺少必要的数据点 '{e.args[0]}'。")
        except ZeroDivisionError:
            raise ValueError(f"策略 '{strategy}' 的计算导致除以零。请检查ROE、ROA或分红率等输入值。")

        return result

marketEarningRatioValuator = MarketEarningRatioValuator()