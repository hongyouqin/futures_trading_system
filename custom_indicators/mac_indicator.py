import backtrader as bt

class MovingAverageCrossOver(bt.Indicator):
    '''
        双均线交叉，快线上窜到慢线以上，表示趋势向上，不许做空；反之趋势向下，不准做多。
    '''
    lines = ('trend','trend_start_price', )
    
    params = (
        ('short_ma_period', 13),   # 短期均线周期（周线级别对应13周）
        ('long_ma_period', 34),    # 长期均线周期（周线级别对应34周）
    )
    
    def __init__(self):
                # 初始化均线指标
        self.short_ma = bt.indicators.SMA(
            self.data.close, period=self.p.short_ma_period, plotname='短期均线'
        )
        self.long_ma = bt.indicators.SMA(
            self.data.close, period=self.p.long_ma_period, plotname='长期均线'
        )
        
        # 记录趋势开始的时间和价格
        self.trend_start_date = None
        self.trend_start_price = None
        self.last_signal = 0  # 记录上一次的信号

    def trend_signal(self):
        '''
            判断趋势
        '''
        if len(self.short_ma) < 1 or len(self.long_ma) < 1:
            return 0
        
        fast_ma = self.short_ma[0]
        slow_ma = self.long_ma[0]
        if fast_ma > slow_ma:
            # 趋势向上
            return 1
        elif fast_ma < slow_ma:
            # 趋势向下
            return -1
        else:
            return 0
    def is_trend_change(self, current_signal):
        '''
        检测趋势是否发生变化
        '''
        # 从无趋势或下跌转为上涨
        if current_signal == 1 and self.last_signal <= 0:
            return True, 'bullish'
        # 从无趋势或上涨转为下跌  
        elif current_signal == -1 and self.last_signal >= 0:
            return True, 'bearish'
        else:
            return False, None   
    
    def get_trend_info(self):
        '''
        获取当前趋势的详细信息
        '''
        return {
            'current_trend': self.lines.trend[0],
            'trend_start_date': self.trend_start_date,
            'trend_start_price': self.trend_start_price,
            'trend_duration': self.get_trend_duration() if self.trend_start_date else 0
        }
    
    def get_trend_duration(self):
        '''
        计算趋势持续时间（天数）
        '''
        if not self.trend_start_date:
            return 0
        
        current_date = self.data.datetime.date(0)
        duration = (current_date - self.trend_start_date).days
        return duration
    
    def next(self):
        current_signal  = self.trend_signal()
        # 检测趋势变化
        trend_changed, trend_type = self.is_trend_change(current_signal)
        
        if trend_changed:
            # 记录新的趋势开始时间和价格
            self.trend_start_date = self.data.datetime.date(0)
            self.trend_start_price = self.data.close[0]
            
            print(f"趋势转变! 时间: {self.trend_start_date}, 价格: {self.trend_start_price:.2f}, 类型: {'上涨' if trend_type == 'bullish' else '下跌'}")
        
        # 更新趋势信号
        self.lines.trend[0] = current_signal
        self.lines.trend_start_price[0] = self.trend_start_price if self.trend_start_price else 0
        
        # 保存当前信号用于下一次比较
        self.last_signal = current_signal
        