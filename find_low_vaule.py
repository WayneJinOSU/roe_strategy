import tushare as ts
import pandas as pd
# 初始化pro接口
pd.set_option('display.max_columns', 100)
pro = ts.pro_api('53ee1462078b0eccca09bc5d0c92e50b13524272e6ef9ea49db0a876')

df = pd.read_csv('/Users/a/PycharmProjects/roe_strategy/result/20251114_low_vaule_stock.csv')
temp = df[df['pr_value']<0.5]
print(temp)