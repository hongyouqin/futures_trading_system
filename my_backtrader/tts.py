import backtrader as bt
from custom_indicators.mac_indicator import MovingAverageCrossOver
from custom_indicators.force_indicator import ForceIndex


class TripleScreenTradingSystem(bt.Strategy):
    '''
     三重过滤交易系统,用于生成期货趋势分析报表，辅助人工交易
    '''
    
    params = (
        ('atr_period', 14),       # ATR计算周期
        ('adx_period', 14),
        ('rsi_period', 14),
        ('symbol', ''),           # 商品代码
    )
    
    def __init__(self):
        # 判断周趋势
        self.trend = MovingAverageCrossOver(self.data1)
        self.force = ForceIndex(self.data)
        self.rsi = bt.indicators.RSI_Safe(self.data.close, period=self.p.rsi_period, safediv=True)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        dmi = bt.indicators.DirectionalMovementIndex(period = self.p.adx_period)
        self.adx = dmi.lines.adx
        
        # 分析报告
        self.analysis_reports = []
        
        # 记录当前日期
        self.current_date = None
    
    def get_trend_text(self, trend_value):
        '''获取趋势文字描述'''
        if trend_value == 1:
            return "上涨"
        elif trend_value == -1:
            return "下跌"
        else:
            return "震荡"
    
    def tsts_analysis(self):
        '''
            三重系统过滤分析
        '''
        trend_info = self.trend.get_trend_info() if hasattr(self.trend, 'get_trend_info') else {}
        report = {
            'date': self.data.datetime.date(0).strftime('%Y-%m-%d'),
            'symbol': self.data._name or '未知商品',
            'close_price': self.data.close[0],
            'trend': self.trend.lines.trend[0],
            'trend_text': self.get_trend_text(self.trend.lines.trend[0]),
            'trend_start_date': trend_info.get('trend_start_date', '未知'),
            'trend_start_price': trend_info.get('trend_start_price', 0),
            'trend_duration': trend_info.get('trend_duration', 0),
            'rsi': round(self.rsi[0], 2) if len(self.rsi) > 0 else 0,
            'atr': round(self.atr[0]) if len(self.atr) > 0 else 0,
            'atr_percent': round((self.atr[0] / self.data.close[0] * 100), 2) if len(self.atr) > 0 and self.data.close[0] != 0 else 0,
            'force_index': round(self.force.lines.force[0], 2) if len(self.force) > 0 else 0,
            'adx': round(self.adx[0], 2) if len(self.adx) > 0 else 0,
            'buy_signal': 0,
            'sell_signal': 0,
            'signal_strength': 0  # 信号强度 0-100
        }
        signal_strength = 0
        
        if self.trend.lines.trend[0] == 1:  # 趋势向上
            conditions_met = 0            
            # 第一重：趋势确认（已满足）
            conditions_met += 1
            
            # 第二重：动量确认
            if self.adx[0] > 25:
                conditions_met += 1
                signal_strength += 30
            if self.force.lines.force[0] < 0:  # 力量指数为负表示回调，是买入机会
                conditions_met += 1
                signal_strength += 30
            
            # 第三重：时机选择
            if self.rsi[0] < 70:  # RSI不过热
                conditions_met += 1
                signal_strength += 20
            
            if conditions_met >= 2:  # 至少满足2个条件
                report['buy_signal'] = 1
                report['signal_strength'] = min(signal_strength + 20, 100)
                
        elif self.trend.lines.trend[0] == -1:  # 趋势向下
            conditions_met = 0
            # 第一重：趋势确认（已满足）
            conditions_met += 1
            
            # 第二重：动量确认
            if self.adx[0] > 25:
                conditions_met += 1
                signal_strength += 30
            if self.force.lines.force[0] > 0:  # 力量指数为正表示反弹，是卖出机会
                conditions_met += 1
                signal_strength += 30
            
            # 第三重：时机选择
            if self.rsi[0] > 30:  # RSI不超卖
                conditions_met += 1
                signal_strength += 20
            
            if conditions_met >= 2:
                report['sell_signal'] = 1
                report['signal_strength'] = min(signal_strength + 20, 100)
        
        # 添加技术指标状态描述
        report['adx_strength'] = "强趋势" if report['adx'] > 25 else "弱趋势"
        report['force_status'] = "看涨" if report['force_index'] < 0 else "看跌" if report['force_index'] > 0 else "中性"
        
        return report
    
    def save_analysis_report(self, report):
        '''保存分析报告'''
        self.analysis_reports.append(report)
        
        # 只在有信号或每周保存详细报告
        if report['buy_signal'] == 1 or report['sell_signal'] == 1:
            self.print_signal_report(report)
    
    def print_signal_report(self, report):
        '''打印信号报告'''
        print("\n" + "="*80)
        print(f"📊 三重过滤交易信号 - {report['date']}")
        print("="*80)
        print(f"商品: {report['symbol']} | 收盘价: {report['close_price']:.2f}")
        print(f"趋势: {report['trend_text']} | 开始日期: {report['trend_start_date']} | 开始价格: {report['trend_start_price']:.2f}")
        print(f"持续时间: {report['trend_duration']}天")
        print("-"*80)
        print(f"技术指标:")
        print(f"  RSI: {report['rsi']:.1f}")
        print(f"  ATR: {report['atr']:.3f} ({report['atr_percent']:.2f}%)")
        print(f"  ADX: {report['adx']:.1f} ({report['adx_strength']})")
        print(f"  力量指数: {report['force_index']:.0f} ({report['force_status']})")
        print("-"*80)
        
        if report['buy_signal'] == 1:
            print(f"🎯 买入信号 | 强度: {report['signal_strength']}%")
        elif report['sell_signal'] == 1:
            print(f"🎯 卖出信号 | 强度: {report['signal_strength']}%")
        else:
            print("⏸️  无交易信号")
        print("="*80)    
        
    def next(self):
        report = self.tsts_analysis()
        self.save_analysis_report(report)
        
    def stop(self):
        '''策略结束时保存最终报告'''
        if not self.analysis_reports:
            print("没有分析报告可保存")
            return
            
        # 获取最新报告
        latest = self.analysis_reports[-1]
        
        # 创建单行DataFrame并保存
        import pandas as pd
        df = pd.DataFrame([latest])
        
        filename = f"triple_screen_latest_{self.data._name}_{self.data.datetime.date(0).strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        # 输出最新状态
        print(f"\n📊 最新分析报告 - {latest['date']}")
        print(f"商品: {latest['symbol']} | 趋势: {latest['trend_text']}")
        print(f"信号: {'买入' if latest['buy_signal'] == 1 else '卖出' if latest['sell_signal'] == 1 else '无'}")
        print(f"📁 已保存至: {filename}")