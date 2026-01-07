import math
import backtrader as bt

import datetime  # For datetime objects
import os.path  # To manage paths
import sys  # To find out the script name (in argv[0])


# from median_indicator import Median

'''
 埃尔德的强力指标：
 计算公式：
 强力指标数值 = （当日收盘价-前一日收盘价） X 当日交易量
 同时为了使图标更平滑，使用EMA进行平滑处理
'''
class ForceIndex(bt.Indicator):
    lines = ('force',)
    params = (('period', 2),)
    
    # 类级别的绘图配置（关键修改点）
    plotinfo = dict(
        plotyhlines=[0],      # 在0轴画参考线
        plothlines=[0],       # 等同于plotyhlines
        plotlinelabels=True,  # 显示线标签
        subplot=True          # 强制显示在副图
    )
    
    plotlines = dict(
        force=dict(color='blue', alpha=0.8),  # 主指标线样式
        _0=dict(color='red', linestyle='--', alpha=0.5)  # 0轴参考线样式
    )
    
    # 使用Backtrader兼容的对数近似计算
    class LogVolume(bt.Indicator):
        lines = ('logvol',)
        def next(self):
            v = self.data.volume[0]
            self.lines.logvol[0] = math.log1p(v) if v > 0 else 0
    
    def __init__(self):
     
        # 使用np.log1p自动处理零值（log(1+x)）
        price_change = self.data.close - self.data.close(-1)
        self.log_volume = self.LogVolume(self.data)
        raw_force = price_change * self.log_volume
        # 对原始 Force Index 计算 EMA 平滑
        self.lines.force = bt.indicators.EMA(raw_force, period = self.p.period)
    
        self.addminperiod(self.p.period + 1)
    # def next(self):
    #      print(f"成交量: {self.log_volume[0]}")
        
