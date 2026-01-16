import backtrader as bt

class TripleMAStateTracker(bt.Indicator):
    '''
    三均线状态跟踪指标（10, 20, 40）
    状态定义：
    1. UPTREND: 10 > 20 > 40 (多头排列)
    2. DOWNTREND: 10 < 20 < 40 (空头排列)
    3. CONSOLIDATION: 其他情况（震荡/横盘）
    
    支持状态连续变化跟踪：
    - CONSOLIDATION → UPTREND
    - CONSOLIDATION → DOWNTREND  
    - DOWNTREND → CONSOLIDATION
    - UPTREND → CONSOLIDATION
    '''
    
    # 状态常量
    CONSOLIDATION = 0
    UPTREND = 1
    DOWNTREND = -1
    
    # 状态变化常量
    NO_CHANGE = 0
    CONSOL_TO_UPTREND = 1
    CONSOL_TO_DOWNTREND = 2
    DOWNTREND_TO_CONSOL = 3
    UPTREND_TO_CONSOL = 4
    UPTREND_TO_DOWNTREND = 5
    DOWNTREND_TO_UPTREND = 6
    
    lines = (
        'trend_state',           # 当前趋势状态: 1(上), -1(下), 0(震荡)
        'state_change',          # 状态变化信号
        'ma10', 'ma20', 'ma40',  # 三条均线值
        'ma_spread_ratio',       # 均线分离度
        'trend_strength',        # 趋势强度评分
        'state_duration',        # 当前状态持续时间
        'is_stable_state',       # 状态是否稳定
    )
    
    params = (
        ('ma1_period', 10),
        ('ma2_period', 20),
        ('ma3_period', 40),
        ('adx_period', 14),
        ('adx_threshold', 22.0),
        ('min_state_duration', 2),     # 最小状态持续时间
        ('stability_period', 3),       # 稳定确认周期
        ('ma_spread_threshold', 0.015), # 均线分离阈值
    )
    
    def __init__(self):
        # 初始化三条EMA均线
        self.ma10 = bt.indicators.EMA(
            self.data.close, period=self.p.ma1_period
        )
        self.ma20 = bt.indicators.EMA(
            self.data.close, period=self.p.ma2_period
        )
        self.ma40 = bt.indicators.EMA(
            self.data.close, period=self.p.ma3_period
        )
        
        # 存储三条均线到lines以便外部访问
        self.lines.ma10 = self.ma10
        self.lines.ma20 = self.ma20
        self.lines.ma40 = self.ma40
        
        # ADX指标用于趋势强度判断
        self.dmi = bt.indicators.DirectionalMovementIndex(
            self.data, period=self.p.adx_period
        )
        self.adx = self.dmi.lines.adx
        
        # ATR用于波动率判断
        self.atr = bt.indicators.ATR(self.data, period=14)
        
        # 状态跟踪变量
        self.current_state = self.CONSOLIDATION
        self.previous_state = self.CONSOLIDATION
        self.state_start_idx = 0
        self.state_changes = []  # 存储状态变化历史
        
        # 用于稳定性判断的历史状态
        self.state_history = []
        
    def calculate_ma_relationship(self):
        '''计算三均线排列关系'''
        if len(self.ma10) < 1 or len(self.ma20) < 1 or len(self.ma40) < 1:
            return None
            
        ma10_val = self.ma10[0]
        ma20_val = self.ma20[0]
        ma40_val = self.ma40[0]
        
        # 检查多头排列
        if ma10_val > ma20_val > ma40_val:
            return self.UPTREND
            
        # 检查空头排列
        if ma10_val < ma20_val < ma40_val:
            return self.DOWNTREND
            
        # 其他情况为震荡
        return self.CONSOLIDATION
    
    def calculate_ma_spread(self):
        '''计算均线分离度'''
        if len(self.ma10) < 1 or len(self.ma20) < 1 or len(self.ma40) < 1:
            return 0
            
        current_price = self.data.close[0]
        if current_price == 0:
            return 0
            
        # 计算最大均线差值比率
        spreads = [
            abs(self.ma10[0] - self.ma20[0]) / current_price,
            abs(self.ma20[0] - self.ma40[0]) / current_price,
            abs(self.ma10[0] - self.ma40[0]) / current_price
        ]
        
        max_spread = max(spreads)
        self.lines.ma_spread_ratio[0] = max_spread
        return max_spread
        
    def get_trend_strength(self):
        '''计算趋势强度评分'''
        strength = 50  # 基础分
        
        # ADX贡献
        if len(self.adx) > 0:
            adx_strength = min(30, (self.adx[0] / 50) * 30)
            strength += adx_strength - 15  # 减去基础分
            
        # 均线分离度贡献
        spread_ratio = self.calculate_ma_spread()
        spread_strength = min(20, (spread_ratio / 0.03) * 20)
        strength += spread_strength - 10
        
        # 均线斜率贡献
        if len(self.ma10) > 5:
            ma10_slope = (self.ma10[0] - self.ma10[-5]) / 5 / self.data.close[0]
            strength += min(10, abs(ma10_slope * 1000))
            
        return max(0, min(100, strength))
    
    def detect_state_change(self):
        '''检测状态变化，并在检测到变化时更新当前状态'''
        new_state = self.calculate_ma_relationship()
        if new_state is None:
            return self.NO_CHANGE
            
        # 检查状态是否真的改变
        if new_state == self.current_state:
            return self.NO_CHANGE
            
        # 确定状态变化类型
        change_type = self.NO_CHANGE
        
        if self.current_state == self.CONSOLIDATION and new_state == self.UPTREND:
            change_type = self.CONSOL_TO_UPTREND
        elif self.current_state == self.CONSOLIDATION and new_state == self.DOWNTREND:
            change_type = self.CONSOL_TO_DOWNTREND
        elif self.current_state == self.DOWNTREND and new_state == self.CONSOLIDATION:
            change_type = self.DOWNTREND_TO_CONSOL
        elif self.current_state == self.UPTREND and new_state == self.CONSOLIDATION:
            change_type = self.UPTREND_TO_CONSOL
        elif self.current_state == self.UPTREND and new_state == self.DOWNTREND:
            change_type = self.UPTREND_TO_DOWNTREND
        elif self.current_state == self.DOWNTREND and new_state == self.UPTREND:
            change_type = self.DOWNTREND_TO_UPTREND
            
        # 如果状态有变化，记录并更新状态
        if change_type != self.NO_CHANGE:
            # 记录状态变化
            self.state_changes.append({
                'date': self.data.datetime.date(0),
                'from': self.current_state,
                'to': new_state,
                'type': change_type,
                'price': self.data.close[0]
            })
            
            # 更新状态（在detect_state_change中直接更新）
            self.previous_state = self.current_state
            self.current_state = new_state
            
        # print(f"{self.datas[0].datetime.datetime(0)}===========打印状态 = {new_state} 当前状态={self.current_state} 状态改变={change_type}")

        
        return change_type
    
    def check_state_stability(self):
        '''检查状态是否稳定'''
        if len(self.state_history) < self.p.stability_period:
            return False
            
        # 检查最近N个周期的状态是否一致
        recent_states = self.state_history[-self.p.stability_period:]
        if all(s == self.current_state for s in recent_states):
            return True
            
        return False
    
    def get_state_duration(self):
        '''获取当前状态持续时间'''
        return len(self.data) - self.state_start_idx
    
    def get_state_info(self):
        '''获取状态详细信息'''
        return {
            'current_state': self.current_state,
            'state_name': {
                self.UPTREND: 'UPTREND',
                self.DOWNTREND: 'DOWNTREND',
                self.CONSOLIDATION: 'CONSOLIDATION'
            }[self.current_state],
            'state_change': self.lines.state_change[0],
            'state_change_name': {
                self.NO_CHANGE: 'NO_CHANGE',
                self.CONSOL_TO_UPTREND: 'CONSOL_TO_UPTREND',
                self.CONSOL_TO_DOWNTREND: 'CONSOL_TO_DOWNTREND',
                self.DOWNTREND_TO_CONSOL: 'DOWNTREND_TO_CONSOL',
                self.UPTREND_TO_CONSOL: 'UPTREND_TO_CONSOL',
                self.UPTREND_TO_DOWNTREND: 'UPTREND_TO_DOWNTREND',
                self.DOWNTREND_TO_UPTREND: 'DOWNTREND_TO_UPTREND'
            }.get(self.lines.state_change[0], 'UNKNOWN'),
            'state_duration': self.lines.state_duration[0],
            'is_stable': self.lines.is_stable_state[0],
            'ma_values': {
                'ma10': self.ma10[0] if len(self.ma10) > 0 else None,
                'ma20': self.ma20[0] if len(self.ma20) > 0 else None,
                'ma40': self.ma40[0] if len(self.ma40) > 0 else None
            },
            'trend_strength': self.lines.trend_strength[0],
            'adx_value': self.adx[0] if len(self.adx) > 0 else None,
            'ma_spread_ratio': self.lines.ma_spread_ratio[0]
        }
    
    def next(self):
        # 计算状态变化
        state_change = self.detect_state_change()
        
        # 更新状态历史
        self.state_history.append(self.current_state)
        if len(self.state_history) > 50:  # 保持合理长度
            self.state_history.pop(0)
        
        # 如果状态改变，更新状态开始索引
        if state_change != self.NO_CHANGE:
            self.state_start_idx = len(self.data)
        
        # 计算状态持续时间
        state_duration = self.get_state_duration()
        
        # 检查状态稳定性
        is_stable = self.check_state_stability() and state_duration >= self.p.min_state_duration
        
        # 更新lines
        self.lines.trend_state[0] = self.current_state
        self.lines.state_change[0] = state_change
        self.lines.state_duration[0] = state_duration
        self.lines.is_stable_state[0] = int(is_stable)
        self.lines.trend_strength[0] = self.get_trend_strength()
        
        # logging.info(f"周期时间:{self.data.datetime.datetime(0)} "
        #          f"当前状态={self.current_state} "
        #          f"趋势改变: {state_change}; "
        #          f"状态历史长度: {len(self.state_history)} "
        #          f"稳定周期要求: {self.p.stability_period} "
        #          f"趋势是否稳定: {int(is_stable)}")
