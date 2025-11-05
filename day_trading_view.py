import argparse
import akshare as ak

import pandas as pd
from custom_indicators.force_indicator import ForceIndex
from custom_indicators.dynamic_value_channel import DynamicValueChannel
import backtrader as bt

class RSIWithEMA(bt.Indicator):
    '''
    自定义RSI指标，包含RSI和RSI_EMA两条线
    在同一个区域显示
    '''
    lines = ('rsi', 'rsi_ema')
    params = (
        ('rsi_period', 14),
        ('ema_period', 9),
    )
    
    def __init__(self):
        # 计算RSI
        self.lines.rsi = bt.indicators.RSI(
            self.data, 
            period=self.p.rsi_period
        )
        # 计算RSI的EMA
        self.lines.rsi_ema = bt.indicators.EMA(
            self.lines.rsi, 
            period=self.p.ema_period
        )
        
        # 设置绘图参数
        # self.plotinfo.plotmaster = self.data  # 在主图区域显示
        self.plotinfo.subplot = True  # 作为子图显示
        
class RSIWith_KD(bt.Indicator):
    '''
    自定义指标，包含RSI、RSI_EMA和KD值
    在同一个区域显示
    '''
    lines = ('k', 'd')
    params = (
        ('kd_period', 14),  # KD计算周期
        ('k_period', 3),    # K值平滑周期
        ('d_period', 3),    # D值平滑周期
    )
    
    def __init__(self):
        # 计算KD指标
        # 计算过去period周期内的最低价和最高价
        self.lowest_low = bt.indicators.Lowest(self.data.low, period=self.p.kd_period)
        self.highest_high = bt.indicators.Highest(self.data.high, period=self.p.kd_period)
        
        # 计算未成熟随机值(RSV)
        rsv = (self.data.close - self.lowest_low) / (self.highest_high - self.lowest_low) * 100
        
        # 计算K值（RSV的k_period期EMA）
        self.lines.k = bt.indicators.EMA(rsv, period=self.p.k_period)
        
        # 计算D值（K值的d_period期EMA）
        self.lines.d = bt.indicators.EMA(self.lines.k, period=self.p.d_period)
        
        self.plotlines.k.lines = True
        self.plotlines.k.color = 'green'
        self.plotlines.k.label = 'K'
        self.plotlines.k._plotskip = False
        
        self.plotlines.d.lines = True
        self.plotlines.d.color = 'orange'
        self.plotlines.d.label = 'D'
        self.plotlines.d._plotskip = False
        
        # 设置区域范围（0-100）
        self.plotinfo.plotymax = 100
        self.plotinfo.plotymin = 0

class TestStrategy(bt.Strategy):
    
    params = (
        ('fast', 8), 
        ('slow', 21),
        ('channel_coeff', 0.152579),
        ('channel_window', 60),
    )
    
    def __init__(self):
        # 技术指标
        self.force_index = ForceIndex(self.data, period=2)
        self.sma_fast = bt.indicators.EMA(period=self.p.fast)
        self.rsiwith_kd = RSIWith_KD(self.data)
        self.rsi = RSIWithEMA(self.data)
        
        # 动态价值通道指标 - 这会自动显示在主图上
        self.value_channel = DynamicValueChannel(
            self.data,
            slow_period=self.p.slow,
            channel_window=self.p.channel_window,
            initial_coeff=self.p.channel_coeff
        )
    
    def next(self):
        # 策略逻辑...
        # 价值通道会自动更新，不需要在这里手动更新
        pass


def parse_args():
    '''
        k线图指标绘制
    '''
    parser = argparse.ArgumentParser(  
        description='期货指标分析')
    parser.add_argument('--symbol', default="", required= True, 
                        help="期货商品编号")
    parser.add_argument('--period', default="15min", 
                        help="周期: daily, weekly")
    return parser.parse_args()

class FuturesDataFeed(bt.feeds.PandasData):
    """适配期货数据的Backtrader数据源"""
    params = (
        ('datetime', 'datetime'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', 'hold'),
    )

if __name__ == '__main__':
    
    args = parse_args()
    
    symbol = args.symbol
    period = args.period
    data_df = ak.futures_zh_minute_sina(symbol=symbol, period=15)
    print(data_df.head())
    cerebro = bt.Cerebro()
    # 添加策略
    cerebro.addstrategy(TestStrategy)
    
    # 准备数据 - 确保日期格式正确
    df = data_df.copy()
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')

    
    data = FuturesDataFeed(dataname=df)
    
    # 添加数据到Cerebro
    cerebro.adddata(data)
    # 运行回测
    results = cerebro.run()
    
    # 绘制图表 - 使用更兼容的方式
    cerebro.plot(style='candle', volume=True, barup='red', bardown='green')
