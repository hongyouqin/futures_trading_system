import backtrader as bt

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