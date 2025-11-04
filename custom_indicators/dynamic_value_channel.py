import backtrader as bt
import numpy as np

class DynamicValueChannel(bt.Indicator):
    """
    动态价值通道指标
    显示在主图上，与价格在同一坐标系
    """
    lines = ('up_channel', 'down_channel', 'middle_line')
    
    # 在类级别设置绘图参数
    plotinfo = dict(
        subplot=False,  # 在主图显示，不在子图
        plotlinelabels=True,  # 显示线条标签
    )
    
    # 设置每条线的绘图参数
    plotlines = dict(
        up_channel=dict(
            color='red',
            linestyle='--',
            _name='上通道'
        ),
        down_channel=dict(
            color='green', 
            linestyle='--',
            _name='下通道'
        ),
        middle_line=dict(
            color='blue',
            linestyle='-',
            _name='中线'
        )
    )
    
    params = (
        ('slow_period', 34),
        ('channel_window', 60),
        ('use_stddev', True),
        ('initial_coeff', 0.152579),
    )
    
    def __init__(self):
        # 中间线就是慢速EMA
        self.lines.middle_line = bt.indicators.EMA(
            self.data, period=self.p.slow_period
        )
        
        if self.p.use_stddev:
            # 标准差法替代（更精确）
            self.stddev = bt.indicators.StdDev(self.data.close, period=self.p.slow_period)
            self.lines.up_channel = self.middle_line + 2 * self.stddev
            self.lines.down_channel = self.middle_line - 2 * self.stddev
        else:
            # 初始化通道线 - 使用Backtrader的运算操作
            self.lines.up_channel = self.lines.middle_line * (1 + self.p.initial_coeff)
            self.lines.down_channel = self.lines.middle_line * (1 - self.p.initial_coeff)        

        
        # 添加ATR指标用于波动率计算
        self.atr = bt.indicators.ATR(self.data, period=14)
        
        # 保存历史系数用于平滑
        self.prev_coeff = self.p.initial_coeff
    
    def calculate_dynamic_coefficient(self):
        """计算动态通道系数"""
        try:
            # 基础检查
            if len(self.data) < 30:
                return self.p.initial_coeff

            # 当前状态计算
            current_price = float(self.data.close[0])
            current_ema = float(self.lines.middle_line[0])
            if current_ema <= 1e-6:
                return self.prev_coeff
                
            current_dev = abs(current_price - current_ema) / current_ema
            
            # 动态上限计算
            max_coeff = min(0.6, 0.3 + current_dev / 2)
            
            # 获取历史数据
            lookback = min(len(self.data), self.p.channel_window)
            if lookback < 10:  # 确保有足够的数据
                return self.p.initial_coeff
                
            closes = np.array(self.data.close.get(size=lookback), dtype=np.float64)
            ema_slow = np.array(self.lines.middle_line.get(size=lookback), dtype=np.float64)
            
            # 多维度波动计算
            with np.errstate(all='ignore'):
                # 相对偏离度
                valid_mask = (ema_slow > 1e-6) & (~np.isnan(closes)) & (~np.isnan(ema_slow))
                if not np.any(valid_mask):
                    return self.prev_coeff
                    
                rel_deviations = np.abs(closes[valid_mask] - ema_slow[valid_mask]) / ema_slow[valid_mask]
                
                # 对数收益率波动
                if len(closes) >= 2:
                    log_returns = np.diff(np.log(closes))
                    vol_returns = np.std(log_returns) * 16 if len(log_returns) > 0 else 0
                else:
                    vol_returns = 0
                    
                # ATR比率
                atr_ratio = 0
                if len(self.atr) >= lookback:
                    atr_values = np.array(self.atr.get(size=lookback), dtype=np.float64)
                    atr_ratio = np.nanmean(atr_values[valid_mask] / ema_slow[valid_mask]) if np.any(valid_mask) else 0
            
            # 动态权重调整
            atr_weight = 0.2 + 0.1 * (1 / (1 + np.exp(-10 * (current_dev - 0.2))))
            weights = np.array([0.5, 0.3, atr_weight])
            weights /= weights.sum()
            
            # 组件处理
            percentile_val = np.nanpercentile(rel_deviations, 95) if len(rel_deviations) > 0 else 0.1
            components = np.array([
                min(percentile_val, 0.3),
                min(vol_returns, 0.2),
                min(atr_ratio, 0.1)
            ])
            
            # 综合计算
            combined_vol = np.dot(weights, components)
            
            # 趋势增强
            trend_factor = 1.0 + 2 * (1 / (1 + np.exp(-5 * (current_dev - 0.15))))
            combined_vol = 0.7 * combined_vol + 0.3 * self.prev_coeff * trend_factor
            
            # 最终限制
            combined_vol = max(0.05, min(max_coeff, combined_vol))
            self.prev_coeff = combined_vol
            
            return combined_vol
            
        except Exception as e:
            # logging.error(f"动态系数计算异常: {str(e)}")
            return self.p.initial_coeff
    
    def next(self):
        if self.p.use_stddev is not True:
            # 每根K线更新动态系数
            new_coeff = self.calculate_dynamic_coefficient()
            
            # 更新通道线
            self.lines.up_channel[0] = self.lines.middle_line[0] * (1 + new_coeff)
            self.lines.down_channel[0] = self.lines.middle_line[0] * (1 - new_coeff)

