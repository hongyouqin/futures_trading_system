import backtrader as bt

class MovingAverageCrossOver(bt.Indicator):
    '''
    增强版双均线趋势过滤器
    新增功能：通过均线粘合度识别震荡市，避免在无趋势行情中交易
    '''
    lines = ('trend', 'trend_start_price', 'consolidation', 'ma_spread_ratio')
    
    params = (
        ('short_ma_period', 13),      # 短期均线周期
        ('long_ma_period', 34),       # 长期均线周期
        ('adx_period', 14),           # ADX计算周期
        ('adx_threshold', 22.0),      # ADX趋势强度阈值
        ('ma_spread_threshold', 0.005),  # 均线粘合阈值（0.5%）
        ('min_trend_duration', 3),    # 最小趋势持续时间（根数）
    )
    
    def __init__(self):
        # 初始化均线指标
        self.short_ma = bt.indicators.EMA(
            self.data.close, period=self.p.short_ma_period
        )
        self.long_ma = bt.indicators.EMA(
            self.data.close, period=self.p.long_ma_period
        )
        
        # 初始化ADX指标
        self.dmi = bt.indicators.DirectionalMovementIndex(
            self.data, period=self.p.adx_period
        )
        self.adx = self.dmi.lines.adx
        
        # 初始化ATR用于波动率判断
        self.atr = bt.indicators.ATR(self.data, period=14)
        
        # 记录变量
        self.trend_start_date = None
        self.trend_start_price = None
        self.last_signal = 0
        self.trend_duration = 0
        
        # 用于均线斜率计算
        self.short_ma_slope = 0
        self.long_ma_slope = 0
    
    def calculate_ma_spread(self):
        '''计算均线粘合度'''
        if len(self.short_ma) < 1 or len(self.long_ma) < 1:
            return 0
            
        fast = self.short_ma[0]
        slow = self.long_ma[0]
        current_price = self.data.close[0]
        
        if current_price == 0:
            return 0
            
        # 计算均线差值比率
        spread_ratio = abs(fast - slow) / current_price
        self.lines.ma_spread_ratio[0] = spread_ratio
        
        return spread_ratio
    
    def calculate_ma_slope(self):
        '''计算均线斜率'''
        if len(self.short_ma) > 5:
            self.short_ma_slope = (self.short_ma[0] - self.short_ma[-5]) / 5
            self.long_ma_slope = (self.long_ma[0] - self.long_ma[-5]) / 5
        return self.short_ma_slope, self.long_ma_slope
    
    def is_consolidation_market(self):
        '''
        判断是否为震荡市
        返回True表示震荡市，False表示趋势市
        '''
        # 1. 检查数据是否足够
        if len(self.data.close) < 20:
            return False
            
        # 2. 计算均线粘合度
        spread_ratio = self.calculate_ma_spread()
        current_price = self.data.close[0]
        
        # 条件1：均线极度粘合（差值小于价格的0.5%）
        condition1 = spread_ratio < self.p.ma_spread_threshold
        
        # 条件2：ADX低于阈值，趋势强度不足
        condition2 = self.adx[0] < self.p.adx_threshold
        
        # 条件3：近期价格波动率低（ATR/价格比率小）
        atr_ratio = self.atr[0] / current_price if current_price > 0 else 0
        condition3 = atr_ratio < 0.01  # 波动率小于1%
        
        # 条件4：均线斜率小（趋势弱）
        short_slope, long_slope = self.calculate_ma_slope()
        slope_threshold = current_price * 0.001  # 斜率阈值
        condition4 = abs(short_slope) < slope_threshold and abs(long_slope) < slope_threshold
        
        # 条件5：价格在均线之间窄幅震荡
        recent_high = max(self.data.high.get(size=20))
        recent_low = min(self.data.low.get(size=20))
        price_range_ratio = (recent_high - recent_low) / current_price
        condition5 = price_range_ratio < 0.03  # 价格波动范围小于3%
        
        # 综合判断：满足任意2个条件即认为是震荡市
        consolidation_conditions = [condition1, condition2, condition3, condition4, condition5]
        if sum(consolidation_conditions) >= 2:
            self.lines.consolidation[0] = 1
            return True
        else:
            self.lines.consolidation[0] = 0
            return False
    
    def get_trend_strength(self):
        '''获取趋势强度评分（0-100）'''
        if len(self.adx) == 0:
            return 0
            
        adx_value = self.adx[0]
        spread_ratio = self.calculate_ma_spread()
        
        # ADX贡献度（0-60分）
        adx_score = min(60, (adx_value / 50) * 60) if adx_value > 0 else 0
        
        # 均线分离度贡献度（0-40分）
        # spread_ratio越小分越低，越大分越高（但超过2%不再加分）
        spread_score = min(40, (spread_ratio / 0.02) * 40) if spread_ratio > 0 else 0
        
        # 均线排列质量（额外加分）
        ma_alignment_score = 0
        if self.short_ma_slope > 0 and self.long_ma_slope > 0:
            ma_alignment_score = 10  # 多头排列
        elif self.short_ma_slope < 0 and self.long_ma_slope < 0:
            ma_alignment_score = 10  # 空头排列
            
        total_score = adx_score + spread_score + ma_alignment_score
        return min(100, total_score)
    
    def trend_signal(self):
        '''判断趋势信号，考虑震荡过滤'''
        if len(self.short_ma) < 1 or len(self.long_ma) < 1:
            return 0
        
        # 检查是否为震荡市
        if self.is_consolidation_market():
            return 0  # 震荡市，无趋势信号
            
        fast_ma = self.short_ma[0]
        slow_ma = self.long_ma[0]
        
        # ADX趋势强度过滤
        if self.adx[0] < self.p.adx_threshold:
            return 0
        
        # 判断趋势方向
        if fast_ma > slow_ma:
            # 新增：检查是否满足最小趋势持续时间
            if self.last_signal == 1:
                self.trend_duration += 1
            else:
                self.trend_duration = 1
                
            # 趋势强度评分
            strength = self.get_trend_strength()
            if strength < 40:  # 趋势强度不足
                return 0
                
            return 1
        elif fast_ma < slow_ma:
            if self.last_signal == -1:
                self.trend_duration += 1
            else:
                self.trend_duration = 1
                
            strength = self.get_trend_strength()
            if strength < 40:
                return 0
                
            return -1
        else:
            return 0
    
    def get_trend_info(self):
        '''获取详细的趋势信息'''
        return {
            'current_trend': self.lines.trend[0],
            'adx_value': self.adx[0] if len(self.adx) > 0 else None,
            'adx_above_threshold': self.adx[0] >= self.p.adx_threshold if len(self.adx) > 0 else False,
            'ma_spread_ratio': self.lines.ma_spread_ratio[0],
            'is_consolidation': self.lines.consolidation[0],
            'trend_strength': self.get_trend_strength(),
            'trend_duration': self.trend_duration,
            'trend_start_date': self.trend_start_date,
            'trend_start_price': self.trend_start_price,
        }
    
    def next(self):
        current_signal = self.trend_signal()
        
        # 检测趋势变化
        if current_signal != self.last_signal:
            self.trend_start_date = self.data.datetime.date(0)
            self.trend_start_price = self.data.close[0]
            self.trend_duration = 1
        
        # 更新信号线
        self.lines.trend[0] = current_signal
        self.lines.trend_start_price[0] = self.trend_start_price if self.trend_start_price else 0
        
        # 保存当前信号
        self.last_signal = current_signal
        