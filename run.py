import pandas as pd

from financial_indicator_simple import analyzer
from market_earning_rate import marketEarningRatioValuator

# 要分析的股票列表


# 导入tushare
import tushare as ts

# 初始化pro接口
pro = ts.pro_api('53ee1462078b0eccca09bc5d0c92e50b13524272e6ef9ea49db0a876')

# 拉取数据
df = pro.stock_basic(**{
    "ts_code": "",
    "name": "",
    "exchange": "",
    "market": "",
    "is_hs": "",
    "list_status": "",
    "limit": "",
    "offset": ""
}, fields=[
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "cnspell",
    "market",
    "list_date",
    "act_name",
    "act_ent_type"
])

for index, row in df.iterrows():
    ts_code = row['ts_code']

trade_date = '20250718'  # 使用一个最近的交易日

def basic_filter(valuation_inputs):
    if valuation_inputs:
        if valuation_inputs['latest_metrics']['total_mv'] < 3000000:
            return True
        else:
            return False
    else:
        return True

evaluation_results = []
for index, row in df.iterrows():
    ts_code = row['ts_code']
    try:
        # 1. 从Tushare获取数据并进行分析
        print(f"--- 正在分析股票: {ts_code} ---")
        valuation_inputs = analyzer.analyze_for_valuation(
            ts_code=ts_code,
            trade_date=trade_date
        )
        if basic_filter(valuation_inputs):
            continue

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
            'inputs': str(result['inputs']),
            'pr_value': result['pr_value'],
            'strategy': result['strategy']
        }
        evaluation_results.append(stock_result)

        df = pd.DataFrame(evaluation_results)
        df.to_csv('low_vaule_stock.csv', index=False)

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