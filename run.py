from financial_indicator_simple import analyzer
from market_earning_rate import marketEarningRatioValuator

try:
    # 1. 从Tushare获取数据并进行分析
    valuation_inputs = analyzer.analyze_for_valuation(
        ts_code='600926.SH',  # 示例：贵州茅台
        trade_date='20250721'  # 使用一个最近的交易日
    )
    print("--- 分析器为估值准备的输入数据 ---")
    print("最新财务指标:", valuation_inputs['latest_metrics'])
    print("历史ROE (5年):", valuation_inputs['roe_history'])
    print("-" * 35, "\n")

    # 2. 将分析结果传入估值器进行计算 (取消注释以运行)
    result = marketEarningRatioValuator.evaluate(
        latest_metrics=valuation_inputs['latest_metrics'],
        roe_history=valuation_inputs['roe_history']
    )

    print("--- 估值器计算结果 ---")
    print(f"选用策略: {result['strategy']}")
    print(f"决策理由: {result['justification']}")
    print(f"计算所需输入: {result['inputs']}")
    print(f"市赚率 (PR) 结果: {result['pr_value']:.4f}")
    print("-" * 35)
except Exception as e:
    print(e)