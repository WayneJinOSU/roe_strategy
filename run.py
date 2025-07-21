from financial_indicator_simple import analyzer
from market_earning_rate import marketEarningRatioValuator

# 要分析的股票列表
stocks_to_analyze = ['600926.SH']  # 示例：杭州联合银行
trade_date = '20250718'  # 使用一个最近的交易日

evaluation_results = []

for ts_code in stocks_to_analyze:
    try:
        # 1. 从Tushare获取数据并进行分析
        print(f"--- 正在分析股票: {ts_code} ---")
        valuation_inputs = analyzer.analyze_for_valuation(
            ts_code=ts_code,
            trade_date=trade_date
        )
        print("最新财务指标:", valuation_inputs['latest_metrics'])
        print("历史ROE (5年):", valuation_inputs['roe_history'])
        print("-" * 35, "\n")

        # 2. 将分析结果传入估值器进行计算
        result = marketEarningRatioValuator.evaluate(
            latest_metrics=valuation_inputs['latest_metrics'],
            roe_history=valuation_inputs['roe_history']
        )

        # 3. 存储结果
        stock_result = {
            'ts_code': ts_code,
            'inputs': result['inputs'],
            'pr_value': result['pr_value'],
            'strategy': result['strategy']
        }
        evaluation_results.append(stock_result)

    except Exception as e:
        print(f"处理 {ts_code} 时发生错误: {e}")
        # Optionally, store error information
        evaluation_results.append({
            'ts_code': ts_code,
            'error': str(e)
        })

print("\n--- 所有股票估值完成 ---")
for res in evaluation_results:
    print(res)
    if 'error' in res:
        print(f"股票: {res['ts_code']}, 错误: {res['error']}")
    else:
        print(f"股票: {res['ts_code']}, 输入: {res['inputs']}, 市赚率 (PR): {res['pr_value']:.4f}, 策略: {res['strategy']}")
print("-" * 35)