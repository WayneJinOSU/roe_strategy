import tushare as ts
import numpy as np
import pandas as pd
from datetime import datetime

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

    def _get_financial_core(self, ts_code: str, period_date: str) -> pd.DataFrame:
        """获取指定报告期的财务核心指标，并筛选掉无效数据。"""
        df = self.pro.fina_indicator(
            ts_code=ts_code,
            period=period_date,
            fields=['ts_code', 'ann_date', 'end_date', 'roe_waa', 'roa_dp', 'eps']
        )
        if not df.empty:
            # 规则 1: 筛选掉关键指标 'roe_waa' 为空的行
            df = df.dropna(subset=['roe_waa'])
            # 规则 2: 按公告日期降序排序，确保最新的公告在前
            df = df.sort_values(by='ann_date', ascending=False)
            # 规则 3: 基于核心财务数据去重，保留最新公告的记录
            financial_cols = ['ts_code', 'end_date', 'roe_waa', 'roa_dp', 'eps']
            df = df.drop_duplicates(subset=financial_cols, keep='first').reset_index(drop=True)

            df['roa_dp'] = df['roa_dp'] * 100
        return df

    def _get_dividend(self, ts_code: str, end_date: str) -> pd.DataFrame:
        """获取指定报告期末的分红数据"""
        dividend_df = self.pro.dividend(
            ts_code=ts_code,
            end_date=end_date,
            fields=["ts_code", "end_date", "div_proc", "cash_div_tax"]
        )
        # 筛选已通过股东大会决议的分红方案
        return dividend_df[dividend_df['div_proc'] == '股东大会通过']

    def _merge_financial_dividend(self, financial_core: pd.DataFrame, dividend: pd.DataFrame) -> pd.DataFrame:
        """
        合并财务数据和分红数据，并计算股息支付率（DPR）。
        """
        if dividend.empty or financial_core.empty:
            financial_core['dpr'] = 0.0
            financial_core['cash_div_tax'] = 0.0
            return financial_core

        # 使用 end_date 进行合并
        merged_data = pd.merge(
            financial_core,
            dividend,
            on='end_date',
            how='left',
            suffixes=('_fin', '_div')
        )

        # 如果EPS为正，则计算DPR，否则为0
        merged_data['dpr'] = np.where(
            merged_data['eps'] > 0,
            merged_data['cash_div_tax'] / merged_data['eps'],
            0.0
        )
        # 填充可能因合并产生的NaN值
        merged_data['dpr'] = merged_data['dpr'].fillna(0.0)
        merged_data['cash_div_tax'] = merged_data['cash_div_tax'].fillna(0.0)

        return merged_data[['ts_code_fin', 'end_date', 'roe_waa', 'roa_dp', 'eps', 'dpr', 'cash_div_tax']].rename(
            columns={'ts_code_fin': 'ts_code'})

    def _get_basic_indicator(self, ts_code: str, trade_date: str) -> pd.DataFrame:
        """获取指定交易日的基本指标（PE、PB等）"""
        return self.pro.daily_basic(
            ts_code=ts_code,
            trade_date=trade_date,
            fields='ts_code,trade_date,pe,pb,total_mv'
        )

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

            # 获取对应财报年度的分红数据
            dividend = self._get_dividend(ts_code, period)
            merged_data = self._merge_financial_dividend(financial_core, dividend)

            if not merged_data.empty:
                all_financials.append(merged_data.iloc[0])  # 取第一行（通常只有一个）

        if not all_financials:
            raise ValueError(f"无法获取 {ts_code} 过去5年的任何年度财务数据。")

        # 按报告期降序排序，确保最新的数据在前
        all_financials.sort(key=lambda x: x['end_date'], reverse=True)
        roe_history = [record['roe_waa'] for record in all_financials]

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

analyzer = StockAnalyzer('53ee1462078b0eccca09bc5d0c92e50b13524272e6ef9ea49db0a876')

# 使用示例
if __name__ == "__main__":
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

    except (ValueError, KeyError) as e:
        print(f"发生错误: {e}")


