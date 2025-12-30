import backtrader as bt

class DonchianChannel(bt.Indicator):
    """
    唐奇安通道指标
    在主图上显示
    """
    lines = ('upper', 'middle', 'lower')
    params = (
        ('period', 20),
    )
    
    def __init__(self):
        # 计算通道
        self.lines.upper = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.lines.lower = bt.indicators.Lowest(self.data.low, period=self.p.period)
        self.lines.middle = (self.lines.upper + self.lines.lower) / 2.0
        
        # 设置绘图参数 - 在主图上显示
        self.plotinfo.subplot = False
        
        # 设置线条样式 - 加粗并调整颜色
        # 上轨：使用深红色，线宽3
        self.plotlines.upper._plotskip = False
        self.plotlines.upper.color = 'darkred'
        self.plotlines.upper.label = 'Donchian Upper'
        self.plotlines.upper._linewidth = 5.0  # 设置线宽
        
        # 下轨：使用深蓝色，线宽3
        self.plotlines.lower._plotskip = False
        self.plotlines.lower.color = 'darkblue'
        self.plotlines.lower.label = 'Donchian Lower'
        self.plotlines.lower._linewidth = 5.0  # 设置线宽
        
        # 中轨：使用橙色虚线，线宽2
        self.plotlines.middle._plotskip = False
        self.plotlines.middle.color = 'orange'
        self.plotlines.middle.label = 'Donchian Middle'
        self.plotlines.middle._linewidth = 4.0  # 设置线宽
        self.plotlines.middle.linestyle = '--'  # 虚线样式