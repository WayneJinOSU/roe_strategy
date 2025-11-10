import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import tushare as ts

from financial_indicator_simple import analyzer
from market_earning_rate import marketEarningRatioValuator


# 初始化pro接口（与 run.py 相同的 Token）
pro = ts.pro_api('4285a180dcd3ddecb6132c49acad9c94cd451bf6c2c2eef824f36203')


def load_stock_list():
    # 拉取全部股票基础信息（参考 run.py）
    stock_df = pro.stock_basic(**{
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
    return stock_df


# 使用最近交易日（与 run.py 保持一致以便复用输出文件）
trade_date = '20250915'


def basic_filter(valuation_inputs):
    if valuation_inputs:
        if valuation_inputs['latest_metrics']['total_mv'] < 3000000:
            return True
        else:
            return False
    else:
        return True


def process_stock(ts_code, name, market):
    def retry_with_backoff(func, kwargs, max_retries=3, backoff_base=0.5):
        last_exc = None
        for attempt in range(max_retries):
            try:
                return func(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(backoff_base * (2 ** attempt))
                else:
                    raise last_exc

    try:
        print(f"--- 正在分析股票: {ts_code} ---")
        valuation_inputs = retry_with_backoff(
            analyzer.analyze_for_valuation,
            {"ts_code": ts_code, "trade_date": trade_date},
            max_retries=3,
            backoff_base=0.5,
        )

        if basic_filter(valuation_inputs):
            return None

        print("最新财务指标:", valuation_inputs['latest_metrics'])
        print("历史ROE (5年):", valuation_inputs['roe_history'])
        print("-" * 35, "\n")

        result = retry_with_backoff(
            marketEarningRatioValuator.evaluate,
            {
                "latest_metrics": valuation_inputs['latest_metrics'],
                "roe_history": valuation_inputs['roe_history'],
            },
            max_retries=2,
            backoff_base=0.3,
        )

        return {
            'ts_code': ts_code,
            'name': name,
            'market': market,
            'total_mv': valuation_inputs['latest_metrics']['total_mv'],
            'inputs': str(result['inputs']),
            'pr_value': result['pr_value'],
            'strategy': result['strategy']
        }

    except Exception as e:
        # 重试用尽后再输出一次错误
        print(f"处理 {ts_code} 最终失败: {e}")
        return {
            'ts_code': ts_code,
            'error': str(e)
        }


def main(max_workers=2):
    stock_df = load_stock_list()

    evaluation_results = []
    tasks = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _, row in stock_df.iterrows():
            ts_code = row['ts_code']
            name = row['name']
            market = row['market']
            tasks.append(executor.submit(process_stock, ts_code, name, market))

        for future in as_completed(tasks):
            res = future.result()
            if res is None:
                continue
            evaluation_results.append(res)

    if evaluation_results:
        result_df = pd.DataFrame(evaluation_results)
        result_df.to_csv(f'{trade_date}_low_vaule_stock.csv', index=False)

    print("\n--- 所有股票估值完成 ---")
    for res in evaluation_results:
        print(res)
        if 'error' in res:
            print(f"股票: {res['ts_code']}, 错误: {res['error']}")
        else:
            print(f"股票: {res['ts_code']}, 输入: {res['inputs']}, 市赚率 (PR): {res['pr_value']:.4f}, 策略: {res['strategy']}")
    print("-" * 35)


if __name__ == "__main__":
    # 可按需调整并发度
    main(max_workers=4)


