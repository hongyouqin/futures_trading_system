import argparse
import math
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
    自定义KD指标 - 集成水平线（next方法）
    '''
    lines = ('k', 'd', 'line75', 'line25', 'line50')
    params = (
        ('period', 14),
        ('period_dfast', 3),
        ('period_dslow', 3),
        ('movav', bt.indicators.MovAv.Exponential),
    )
    
    plotinfo = dict(
        plotymax=100,
        plotymin=0
    )
    
    def __init__(self):
        # 计算KD值
        ll = bt.indicators.Lowest(self.data.low, period=self.p.period)
        hh = bt.indicators.Highest(self.data.high, period=self.p.period)
        
        denom = hh - ll
        rsv = 100.0 * (self.data.close - ll) / (denom + 1e-10)
        rsv = bt.Max(0.0, bt.Min(100.0, rsv))
        
        self.lines.k = self.p.movav(rsv, period=self.p.period_dfast)
        self.lines.d = self.p.movav(self.lines.k, period=self.p.period_dslow)
        
        # 设置样式
        # 正确的设置方法 - 使用标准的plotlines属性
        self.plotlines.line75.linestyle = '--'
        self.plotlines.line75.color = 'red'
        self.plotlines.line75.label = 'OB 75'
        self.plotlines.line75._linewidth = 2.5  # 或者 linewidth

        self.plotlines.line25.linestyle = '--'
        self.plotlines.line25.color = 'blue'
        self.plotlines.line25.label = 'OS 25'
        self.plotlines.line25._linewidth = 2.5  # 或者 linewidth

        self.plotlines.line50.linestyle = ':'  # 虚线
        self.plotlines.line50.color = 'gray'
        self.plotlines.line50.label = 'MID 50'
        self.plotlines.line50._linewidth = 1.5  # 或者 linewidth
        
    def next(self):
        # 确保水平线有正确的值
        self.lines.line75[0] = 75
        self.lines.line25[0] = 25
        self.lines.line50[0] = 50

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
        self.atr = bt.indicators.ATR(period = 14)
        
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
        current_up_channel = self.value_channel.lines.up_channel[0]
        current_down_channel = self.value_channel.lines.down_channel[0]
        print(f"时间={self.data.datetime.date(0).strftime('%Y-%m-%d %H:%M'),} atr={self.atr[0]}，价值上通道={current_up_channel}, 价值下通道={current_down_channel}")


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
    data_df = ak.futures_zh_minute_sina(symbol=symbol, period=30)
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
    cerebro.plot(style='candle', volume=True, barup='red', bardown='green', 
             title=f'{symbol} {period} 期货分析')
