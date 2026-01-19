import argparse
import math
import akshare as ak
import pandas as pd
from custom_indicators.donchian_channel import DonchianChannel
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
        self.plotlines.line75.linestyle = '--'
        self.plotlines.line75.color = 'red'
        self.plotlines.line75.label = 'OB 75'

        self.plotlines.line25.linestyle = '--'
        self.plotlines.line25.color = 'blue'
        self.plotlines.line25.label = 'OS 25'

        self.plotlines.line50.linestyle = ':'  # 虚线
        self.plotlines.line50.color = 'gray'
        self.plotlines.line50.label = 'MID 50'
        
    def next(self):
        # 确保水平线有正确的值
        self.lines.line75[0] = 75
        self.lines.line25[0] = 25
        self.lines.line50[0] = 50

# 创建一个专门的持仓量绘图指标
class HoldIndicator(bt.Indicator):
    '''持仓量绘图指标'''
    lines = ('hold', 'hold_sma', 'hold_ema')
    plotinfo = dict(
        plotname='持仓量',
        subplot=True,
        plotlinelabels=True,
    )
    
    def __init__(self):
        if hasattr(self.data, 'hold'):
            self.lines.hold = self.data.hold
            self.lines.hold_sma = bt.indicators.SMA(
                self.data.hold, 
                period=20
            )
            self.lines.hold_ema = bt.indicators.EMA(
                self.data.hold, 
                period=10
            )
            
            # 设置线条样式
            self.plotlines.hold.label = '持仓量'
            self.plotlines.hold.color = 'blue'
            self.plotlines.hold_sma.label = 'MA20'
            self.plotlines.hold_sma.color = 'orange'
            self.plotlines.hold_ema.label = 'EMA10'
            self.plotlines.hold_ema.color = 'red'
            self.plotlines.hold_ema.linestyle = '--'

class TestStrategy(bt.Strategy):
    
    params = (
        ('fast', 10), 
        ('slow', 20),
        ('channel_coeff', 0.152579),
        ('channel_window', 60),
        ('donchian_period', 20),
        ('hold_period', 20),  # 持仓量指标周期
    )
    
    def __init__(self):
        # 技术指标
        self.force_index = ForceIndex(self.data, period=3)
        self.sma_fast = bt.indicators.EMA(period=self.p.fast)
        self.rsiwith_kd = RSIWith_KD(self.data)
        self.atr = bt.indicators.ATR(period=14)
        
        # 动态价值通道指标
        self.value_channel = DynamicValueChannel(
            self.data,
            slow_period=self.p.slow,
            channel_window=self.p.channel_window,
            initial_coeff=self.p.channel_coeff
        )
        
        # 唐奇安通道
        self.donchian = DonchianChannel(
            self.data,
            period=self.p.donchian_period
        )
        
        # MACD Histogram指标 - 设置为子图显示
        self.macd_histo = bt.indicators.MACDHisto(
            self.data.close,
            period_me1=12,
            period_me2=26,
            period_signal=9
        )
        self.macd_histo.plotinfo.subplot = True  # MACD作为子图
        
        # 为了方便访问，可以创建一些别名
        self.macd_line = self.macd_histo.macd
        self.macd_signal = self.macd_histo.signal
        self.macd_histogram = self.macd_histo.histo
        
        # 检查是否有hold字段（持仓量）
        self.has_hold = hasattr(self.data, 'hold') and self.data.hold[0] is not None
        
        if self.has_hold:
            # 添加持仓量绘图指标
            self.hold_indicator = HoldIndicator(self.data)
            
            # 持仓量数据
            self.hold = self.data.hold
            
            # 持仓量简单移动平均
            self.hold_sma = bt.indicators.SMA(
                self.data.hold,
                period=self.p.hold_period
            )
            
            # 持仓量指数移动平均
            self.hold_ema = bt.indicators.EMA(
                self.data.hold,
                period=self.p.hold_period
            )
            
            # 持仓量最高值（N周期）
            self.hold_high = bt.indicators.Highest(
                self.data.hold,
                period=self.p.hold_period
            )
            
            # 持仓量最低值（N周期）
            self.hold_low = bt.indicators.Lowest(
                self.data.hold,
                period=self.p.hold_period
            )
            
            # 持仓量金叉死叉信号的短期和长期均线
            self.hold_short_ma = bt.indicators.SMA(self.data.hold, period=5)
            self.hold_long_ma = bt.indicators.SMA(self.data.hold, period=20)
        else:
            print("警告：数据源没有持仓量（hold）数据")
        
        # 初始化信号变量
        self.hold_breakout_high = False
        self.hold_breakout_low = False
        self.hold_golden_cross = False
        self.hold_dead_cross = False
        self.hold_change = 0
        self.hold_change_pct = 0
        self.hold_volume_ratio = 0
    
    def next(self):
        # 在每次迭代开始时重置信号
        self.hold_breakout_high = False
        self.hold_breakout_low = False
        self.hold_golden_cross = False
        self.hold_dead_cross = False
        
        current_up_channel = self.value_channel.lines.up_channel[0]
        current_down_channel = self.value_channel.lines.down_channel[0]
        donchian_up = round(self.donchian.lines.upper[0], 2)
        donchian_mid = round(self.donchian.lines.middle[0], 2)
        donchian_down = round(self.donchian.lines.lower[0], 2)

        # 获取MACD值
        macd_line = round(self.macd_line[0], 4)
        macd_signal = round(self.macd_signal[0], 4)
        macd_histogram = round(self.macd_histogram[0], 4)
        
        # 获取持仓量信息
        hold_info = ""
        if self.has_hold:
            current_hold = int(self.hold[0]) if self.hold[0] is not None else 0
            hold_sma = int(self.hold_sma[0]) if self.hold_sma[0] is not None else 0
            hold_ema = int(self.hold_ema[0]) if self.hold_ema[0] is not None else 0
            
            # 计算持仓量变化（只在有足够数据时）
            if len(self.hold) > 1 and self.hold[-1] is not None:
                self.hold_change = self.hold[0] - self.hold[-1]
                if self.hold[-1] != 0:
                    self.hold_change_pct = (self.hold[0] - self.hold[-1]) / self.hold[-1] * 100
                else:
                    self.hold_change_pct = 0
            else:
                self.hold_change = 0
                self.hold_change_pct = 0
            
            # 计算持仓量与成交量比率
            if self.data.volume[0] is not None and self.data.volume[0] > 0:
                self.hold_volume_ratio = self.hold[0] / self.data.volume[0] if self.hold[0] is not None else 0
            else:
                self.hold_volume_ratio = 0
            
            # 检查持仓量突破信号（只在有足够数据时）
            if len(self.hold_high) > 0 and self.hold_high[-1] is not None:
                self.hold_breakout_high = self.hold[0] > self.hold_high[-1]
                self.hold_breakout_low = self.hold[0] < self.hold_low[-1]
            
            # 检查持仓量金叉死叉信号
            if (len(self.hold_short_ma) > 0 and len(self.hold_long_ma) > 0 and
                self.hold_short_ma[0] is not None and self.hold_long_ma[0] is not None):
                if len(self.hold_short_ma) > 1 and len(self.hold_long_ma) > 1:
                    self.hold_golden_cross = (self.hold_short_ma[0] > self.hold_long_ma[0] and 
                                              self.hold_short_ma[-1] <= self.hold_long_ma[-1])
                    self.hold_dead_cross = (self.hold_short_ma[0] < self.hold_long_ma[0] and 
                                            self.hold_short_ma[-1] >= self.hold_long_ma[-1])
            
            hold_info = (f"持仓量={current_hold:,}, "
                        f"持仓量MA={hold_sma:,}, "
                        f"持仓量EMA={hold_ema:,}, "
                        f"持仓变化={int(self.hold_change):+,}, "
                        f"持仓变化%={round(self.hold_change_pct, 2)}%, "
                        f"持仓/成交量={round(self.hold_volume_ratio, 2)}")
            
            # 添加持仓量信号信息
            if self.hold_breakout_high:
                hold_info += " [持仓量创新高]"
            if self.hold_breakout_low:
                hold_info += " [持仓量创新低]"
            if self.hold_golden_cross:
                hold_info += " [持仓量金叉]"
            if self.hold_dead_cross:
                hold_info += " [持仓量死叉]"
        
        print(f"时间={self.data.datetime.datetime(0).strftime('%Y-%m-%d %H:%M')} "
              f"突破上通道={donchian_up} 突破中通道={donchian_mid} 突破下通道={donchian_down} "
              f"atr={self.atr[0]:.2f}, "
              f"价值上通道={current_up_channel:.2f}, 价值下通道={current_down_channel:.2f}, "
              f"MACD={macd_line}, 信号线={macd_signal}, 柱状图={macd_histogram}, "
              f"{hold_info}")
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                order_type = "买入"
            elif order.issell():
                order_type = "卖出"
            
            # 在订单通知中也显示持仓量信息
            if self.has_hold:
                current_hold = int(self.hold[0]) if self.hold[0] is not None else 0
                hold_info = f"当前持仓量={current_hold:,}"
            else:
                hold_info = ""
                
            print(f"{self.data.datetime.datetime(0)}: {order_type}执行, 价格={order.executed.price:.2f}, "
                  f"成本={order.executed.value:.2f}, 佣金={order.executed.comm:.2f}, {hold_info}")

def parse_args():
    '''
        k线图指标绘制
    '''
    parser = argparse.ArgumentParser(  
        description='期货指标分析')
    parser.add_argument('--symbol', default="", required=True, 
                        help="期货商品编号")
    parser.add_argument('--period', default="15min", 
                        help="周期: 5min, 15min, 30min")
    return parser.parse_args()

class FuturesDataFeed(bt.feeds.PandasData):
    """适配期货数据的Backtrader数据源"""
    lines = ('hold',)  # 添加持仓量线
    
    params = (
        ('datetime', 'datetime'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),  # 不使用openinterest
        ('hold', 'hold'),  # 指定hold字段
    )

def main():
    args = parse_args()
    
    symbol = args.symbol
    period = args.period
    
    # 获取数据
    try:
        data_df = ak.futures_zh_minute_sina(symbol=symbol, period=period)
        print(f"获取到 {len(data_df)} 条数据")
        print(data_df.head())
    except Exception as e:
        print(f"获取数据失败: {e}")
        return
    
    # 准备数据
    df = data_df.copy()
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')
    
    # 重置索引
    df = df.reset_index(drop=True)
    
    # 创建Cerebro引擎
    cerebro = bt.Cerebro()
    
    # 添加策略
    cerebro.addstrategy(TestStrategy)
    
    # 准备数据
    data = FuturesDataFeed(dataname=df)
    
    # 添加数据到Cerebro
    cerebro.adddata(data)
    
    # 设置初始资金
    cerebro.broker.setcash(1000000.0)
    
    # 设置手续费
    cerebro.broker.setcommission(commission=0.0005)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # 运行回测
    print('初始资金: %.2f' % cerebro.broker.getvalue())
    
    try:
        results = cerebro.run()
        print('最终资金: %.2f' % cerebro.broker.getvalue())
        
        # 输出分析结果
        if results:
            strat = results[0]
            print('夏普比率:', strat.analyzers.sharpe.get_analysis())
            print('最大回撤:', strat.analyzers.drawdown.get_analysis())
            print('收益率:', strat.analyzers.returns.get_analysis())
        
        # 绘制图表
        print("\n正在绘制图表...")
        
        # 简单绘图
        cerebro.plot(style='candle', 
                     volume=True, 
                     barup='red', 
                     bardown='green',
                     title=f'{symbol} {period} 期货分析',
                     figsize=(16, 10))
    
    except Exception as e:
        print(f"运行回测时发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()