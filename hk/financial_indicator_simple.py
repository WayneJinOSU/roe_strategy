import tushare as ts
import numpy as np
import pandas as pd
from datetime import datetime
import time
import random

# from .market_earning_ratio_valuator import MarketEarningRatioValuator


class StockAnalyzer:
    def __init__(self, token: str):
        """
        初始化StockAnalyzer类

        :param token: Tushare Pro API token
        """
        if not token:
            raise ValueError("Tushare Pro API token is required.")
        self.pro = ts.pro_api(token)

    def _query_with_retry(self, query_callable, kwargs, max_retries: int = 3, backoff_base: float = 0.5):
        """
        对 Tushare 查询增加重试与指数退避，并在成功后小睡 0.2s 以限流。
        """
        last_exc = None
        for attempt in range(max_retries):
            try:
                result = query_callable(**kwargs)
                # 成功后做轻微等待，降低速率（并发下尤为重要）
                time.sleep(1)
                return result
            except Exception as exc:  # noqa: BLE001 - 需要捕获第三方库抛出的通用异常
                last_exc = exc
                message = str(exc)
                is_rate_limit = (
                    '每分钟最多访问' in message
                    or 'frequency' in message.lower()
                    or 'too many' in message.lower()
                    or 'rate' in message.lower()
                )
                # 对偶发错误统一重试，频控错误采用退避
                if attempt < max_retries - 1:
                    sleep_secs = backoff_base * (2 ** attempt) + random.uniform(0, 0.2)
                    # 若明显是频控错误，适当增加等待
                    if is_rate_limit:
                        sleep_secs += 0.5
                    time.sleep(sleep_secs)
                    continue
                # 重试用尽后抛出
                raise last_exc

    def _get_financial_core(self, ts_code: str, period_date: str) -> pd.DataFrame:
        """获取指定报告期的财务核心指标，并筛选掉无效数据。"""
        df = self._query_with_retry(
            self.pro.hk_fina_indicator,
            {
                'ts_code': ts_code,
                'period': period_date,
                "report_type": 'Q4',
                'fields': ['ts_code',  "start_date", 'end_date', 'roe_avg', 'roa', 'basic_eps', 'divi_ratio']
            }
        )
        if not df.empty:
            # 规则 1: 筛选掉关键指标 'roe_avg' 为空的行
            df = df.dropna(subset=['roe_avg'])
            # 规则 2: 基于核心财务数据去重，保留最新公告的记录
            financial_cols = ['ts_code', 'end_date', 'roe_avg', 'roa', 'basic_eps', 'divi_ratio']
            df = df.drop_duplicates(subset=financial_cols, keep='first').reset_index(drop=True)
            df['roa'] = df['roa'] * 100

        return df

    def _get_basic_indicator(self, ts_code: str, trade_date: str) -> pd.DataFrame:
        """获取指定交易日的基本指标（PE、PB等）"""
        year = str(trade_date[:4])
        period_date = f'{year}1231'

        df_eps = self._query_with_retry(
            self.pro.hk_fina_indicator,
            {
                'ts_code': ts_code,
                'period': period_date,
                "report_type": 'Q4',
                'fields': ['ts_code', 'end_date', 'basic_eps', 'bps']
            }
        )
        df_close_price = self._query_with_retry(
            self.pro.hk_daily_adj,
            {
                'ts_code': ts_code,
                'trade_date': trade_date,
                'fields': ['ts_code','trade_date','close', 'total_mv']
            }
        )

        # Merge the two DataFrames on the common column 'ts_code'
        df = pd.merge(df_close_price, df_eps, on='ts_code')

        # Ensure numeric types for calculation, converting errors to NaN
        for col in ['close', 'basic_eps', 'bps']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate PE (Price-to-Earnings) ratio.
        # If basic_eps is not positive, PE is not meaningful, so we set it to NaN.
        df['pe'] = np.where(df['basic_eps'] > 0, df['close'] / df['basic_eps'], np.nan)

        # Calculate PB (Price-to-Book) ratio.
        # If bps is not positive, PB is not meaningful, so we set it to NaN.
        df['pb'] = np.where(df['bps'] > 0, df['close'] / df['bps'], np.nan)

        return df

    def analyze_for_valuation(self, ts_code: str, trade_date: str) -> dict:
        """
        获取最近5年的财务数据，并汇总成适用于 MarketEarningRatioValuator 的格式。

        :param ts_code: 股票代码，如 '600926.SH'
        :param trade_date: 当前的交易日期，如 '20240718'
        :return: 包含 latest_metrics 和 roe_history 的字典
        """
        trade_dt = datetime.strptime(trade_date, '%Y%m%d')
        # 获取过去五年的年度报告期（例如，如果今天2024年，则获取2023-2019年的年报）
        report_dates = [f"{year}1231" for year in range(trade_dt.year - 1, trade_dt.year - 6, -1)]

        all_financials = []

        for period in report_dates:
            financial_core = self._get_financial_core(ts_code, period)
            if financial_core.empty:
                continue

            all_financials.append(financial_core.iloc[0])  # 取第一行（通常只有一个）

        if not all_financials:
            raise ValueError(f"无法获取 {ts_code} 过去5年的任何年度财务数据。")

        # 按报告期降序排序，确保最新的数据在前
        all_financials.sort(key=lambda x: x['end_date'], reverse=True)
        roe_history = [record['roe'] for record in all_financials]

        # 计算最近2-4年的平均股息支付率
        dprs = [record['dpr'] for record in all_financials[1:4]]
        if dprs:
            avg_dpr = np.mean(dprs)
        else:
            avg_dpr = 0.0  # 如果没有足够的数据（少于2年），则默认为0

        # 获取最新的财务数据和估值指标
        latest_financials = all_financials[0]
        basic_indicator = self._get_basic_indicator(ts_code, trade_date)
        if basic_indicator.empty:
            raise ValueError(f"无法获取 {ts_code} 在 {trade_date} 的基本估值指标。")

        latest_metrics = {
            'pe': basic_indicator['pe'].iloc[0],
            'pb': basic_indicator['pb'].iloc[0],
            'total_mv': basic_indicator['total_mv'].iloc[0],
            'roa': latest_financials['roa_dp'],
            'dividend_payout_ratio': avg_dpr
        }

        return {
            'latest_metrics': latest_metrics,
            'roe_history': roe_history
        }

analyzer = StockAnalyzer('4285a180dcd3ddecb6132c49acad9c94cd451bf6c2c2eef824f36203')

# 使用示例
if __name__ == "__main__":
    try:
        pro = ts.pro_api("4285a180dcd3ddecb6132c49acad9c94cd451bf6c2c2eef824f36203")

        # 设置你的token
        df = pro.user(token='4285a180dcd3ddecb6132c49acad9c94cd451bf6c2c2eef824f36203')

        print(df)

        # 1. 从Tushare获取数据并进行分析
        valuation_inputs = analyzer.analyze_for_valuation(
            ts_code='00700.hk',  # 示例：贵州茅台
            trade_date='20250721'  # 使用一个最近的交易日
        )
        print("--- 分析器为估值准备的输入数据 ---")
        print("最新财务指标:", valuation_inputs['latest_metrics'])
        print("历史ROE (5年):", valuation_inputs['roe_history'])
        print("-" * 35, "\n")

    except (ValueError, KeyError) as e:
        print(f"发生错误: {e}")


