import logging
import backtrader as bt
import numpy as np
import pandas as pd
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
        ('printlog', True),       # 添加这个参数来控制日志输出
        # 移动止损参数
        ('atr_multiplier', 2),      # ATR倍数
        ('profit_start', 0.05),       # 盈利5%启动移动止损
        ('max_loss', 0.2),           # 单笔最大亏损10%
        ('stage1_profit', 0.08),      # 阶段1：5%盈利
        ('stage1_trail', 0.04),       # 回撤4%平仓
        ('stage2_profit', 0.10),      # 阶段2：10%盈利  
        ('stage2_trail', 0.03),       # 回撤3%平仓
        ('stage3_profit', 0.20),      # 阶段3：20%盈利
        ('stage3_trail', 0.02),       # 回撤2%平仓
        ('symbol', ''),       # 商品代号
        ('max_hold_days', 21),        # 最大持仓30天
        ('oi_lookback', 252*10),         # 持仓量分位数计算周期（5年）
        ('oi_threshold', 0.7),        # 持仓量高位阈值
    )
    
    def __init__(self):
        # 判断周趋势
        self.trend = MovingAverageCrossOver(self.data1)
        self.force = ForceIndex(self.data)
        self.rsi = bt.indicators.RSI_Safe(self.data.close, period=self.p.rsi_period, safediv=True)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        dmi = bt.indicators.DirectionalMovementIndex(period = self.p.adx_period)
        self.adx = dmi.lines.adx
        
        # 持仓量分析指标
        self.volume = self.data.volume
        self.open_interest = self.data.openinterest
        
        # 分析报告
        self.analysis_reports = []
        
        # 记录当前日期
        self.current_date = None
        
        # 交易相关变量
        self.order = None
        self.trade_count = 0
        self.win_count = 0
        self.total_return = 0.0
        
        # 用于记录交易
        self.trades = []
        
        # 记录开仓信息
        self.entry_price = 0
        self.entry_date = None
        self.position_direction = None
        
        # 移动止损相关变量
        self.trailing_stop = 0  # 移动止损位
        self.peak_price = 0     # 峰值价格记录
        
        # 添加时间止损相关变量
        self.entry_bar = 0
        self.current_bar = 0
        
        # 添加状态跟踪
        self.position_opened = False  # 标记是否已开仓
        
        # 持仓量历史数据存储
        self.oi_history = []
        self.volume_history = []

    def log(self, txt, dt=None, doprint=False):
        '''正确的日志函数'''
        if self.params.printlog or doprint:
            dt = dt or self.data.datetime.date(0)
            print(f'{dt.isoformat()}: {txt}')
    
    def calculate_oi_quantile(self, current_oi, lookback_period=252):
        """
        计算当前持仓量在历史中的分位数位置
        """
        if len(self.oi_history) < lookback_period:
            # 数据不足时返回中性值
            return 0.5
        
        # 计算当前持仓量在历史中的分位数
        oi_array = np.array(self.oi_history[-lookback_period:])
        quantile = np.sum(oi_array <= current_oi) / len(oi_array)
        return quantile
    
    def analyze_market_strength(self, price_change, volume_change, oi_change, oi_quantile):
        """
        分析市场强度基于价格、成交量、持仓量关系
        返回: 市场强度描述和分数 (1: 坚挺, -1: 疲软, 0: 中性)
        """
        # 规则1: 价格上涨 + 成交量增加 + 持仓兴趣上升 = 坚挺
        if price_change > 0 and volume_change > 0 and oi_change > 0:
            return "市场坚挺: 价涨量增仓升", 1
        
        # 规则2: 价格上涨 + 成交量减少 + 持仓兴趣下降 = 疲软
        elif price_change > 0 and volume_change < 0 and oi_change < 0:
            return "市场疲软: 价涨量减仓降", -1
        
        # 规则3: 价格下跌 + 成交量减少 + 持仓兴趣下降 = 坚挺
        elif price_change < 0 and volume_change < 0 and oi_change < 0:
            return "市场坚挺: 价跌量减仓降", 1
        
        # 规则4: 价格下跌 + 成交量增加 + 持仓兴趣上升 = 疲软
        elif price_change < 0 and volume_change > 0 and oi_change > 0:
            return "市场疲软: 价跌量增仓升", -1
        
        # 考虑持仓量分位数
        elif oi_quantile > self.p.oi_threshold:
            return f"持仓量极端高位({oi_quantile:.1%})，谨慎操作", -1
        elif oi_quantile < 0.3:
            return f"持仓量极端低位({oi_quantile:.1%})，可能存在机会", 1
        else:
            return "市场中性: 信号不明确", 0

    def get_volume_change(self):
        """计算成交量变化率"""
        if len(self.volume) < 2:
            return 0
        return (self.volume[0] - self.volume[-1]) / self.volume[-1] if self.volume[-1] != 0 else 0

    def get_oi_change(self):
        """计算持仓量变化率"""
        if len(self.open_interest) < 2:
            return 0
        return (self.open_interest[0] - self.open_interest[-1]) / self.open_interest[-1] if self.open_interest[-1] != 0 else 0

    def get_price_change(self):
        """计算价格变化率"""
        if len(self.data.close) < 2:
            return 0
        return (self.data.close[0] - self.data.close[-1]) / self.data.close[-1] if self.data.close[-1] != 0 else 0
    
    def reset_stop_variables(self):
        """
        重置止损相关变量（开仓时调用）
        """
        self.trailing_stop = 0
        self.peak_price = self.data.close[0]
    
    def calculate_trailing_stop(self):
        """
        计算移动止损位 - 基于ATR和分阶段止盈
        返回: 是否触发止损
        """
        if not self.position:
            return False
            
        # 安全检查：确保entry_price有效
        if self.entry_price == 0:
            self.log(f'⚠️ 移动止损检查跳过: entry_price为0')
            return False
            
        current_price = self.data.close[0]
        direction = 1 if self.position.size > 0 else -1
        
        # 安全计算收益率
        try:
            profit_pct = (current_price - self.entry_price) / self.entry_price * 100 * direction
        except ZeroDivisionError:
            self.log(f'❌ 收益率计算错误: entry_price为0')
            return False
        
        # 最大亏损止损
        if profit_pct <= -self.p.max_loss * 100:
            self.log(f'最大亏损止损触发: 收益率={profit_pct:.1f}%')
            return True
        
        # 多头持仓
        if self.position.size > 0:
            # 更新峰值价格
            self.peak_price = max(self.peak_price, current_price)
            
            # 分阶段止盈策略
            stop_price = self.calculate_stage_stop(current_price, profit_pct)
            
            # ATR移动止损（盈利达到启动条件后启用）
            if profit_pct >= self.p.profit_start * 100:
                atr_stop = self.peak_price - self.atr[0] * self.p.atr_multiplier
                stop_price = max(stop_price, atr_stop)
            
            # 触发止损检查
            if current_price <= stop_price:
                self.log(f'多头移动止损触发: 价格={current_price:.2f}, 收益率={profit_pct:.1f}%, 止损价={stop_price:.2f}')
                return True
                
        # 空头持仓
        elif self.position.size < 0:
            # 更新谷值价格
            self.peak_price = min(self.peak_price, current_price)
            
            # 分阶段止盈策略
            stop_price = self.calculate_stage_stop(current_price, profit_pct)
            
            # ATR移动止损
            if profit_pct >= self.p.profit_start * 100:
                atr_stop = self.peak_price + self.atr[0] * self.p.atr_multiplier
                stop_price = min(stop_price, atr_stop)
            
            # 触发止损检查
            if current_price >= stop_price:
                self.log(f'空头移动止损触发: 价格={current_price:.2f}, 收益率={profit_pct:.1f}%, 止损价={stop_price:.2f}')
                return True
        
        return False
    
    def calculate_stage_stop(self, current_price, profit_pct):
        """
        分阶段计算止损位
        """
        # 安全检查
        if self.entry_price == 0:
            return current_price * 0.9  # 默认止损10%
            
        if self.position.size > 0:  # 多头
            if profit_pct >= self.p.stage3_profit * 100:
                # 阶段3：盈利20%以上，紧密跟踪
                return current_price * (1 - self.p.stage3_trail)
            elif profit_pct >= self.p.stage2_profit * 100:
                # 阶段2：盈利10-20%，中等跟踪
                return current_price * (1 - self.p.stage2_trail)
            elif profit_pct >= self.p.stage1_profit * 100:
                # 阶段1：盈利5-10%，宽松跟踪
                return current_price * (1 - self.p.stage1_trail)
            else:
                # 未达到盈利条件，使用固定止损
                return self.entry_price * (1 - self.p.max_loss)
                
        else:  # 空头
            if profit_pct >= self.p.stage3_profit * 100:
                return current_price * (1 + self.p.stage3_trail)
            elif profit_pct >= self.p.stage2_profit * 100:
                return current_price * (1 + self.p.stage2_trail)
            elif profit_pct >= self.p.stage1_profit * 100:
                return current_price * (1 + self.p.stage1_trail)
            else:
                return self.entry_price * (1 + self.p.max_loss)
    
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
        
        # 收集历史数据
        if len(self.open_interest) > 0:
            self.oi_history.append(float(self.open_interest[0]))
        if len(self.volume) > 0:
            self.volume_history.append(float(self.volume[0]))
        
        # 限制历史数据长度
        max_history = self.p.oi_lookback * 2
        if len(self.oi_history) > max_history:
            self.oi_history = self.oi_history[-max_history:]
        if len(self.volume_history) > max_history:
            self.volume_history = self.volume_history[-max_history:]
        
        trend_info = self.trend.get_trend_info() if hasattr(self.trend, 'get_trend_info') else {}
        current_trend = int(self.trend.lines.trend[0])
        current_force = float(self.force.lines.force[0]) if len(self.force) > 0 else 0
        
        # 计算持仓量分位数
        current_oi = float(self.open_interest[0]) if len(self.open_interest) > 0 else 0
        oi_quantile = self.calculate_oi_quantile(current_oi, self.p.oi_lookback)
        
        # 计算变化率
        price_change = self.get_price_change()
        volume_change = self.get_volume_change()
        oi_change = self.get_oi_change()
        
        # 分析市场强度
        market_strength_text, market_strength_score = self.analyze_market_strength(
            price_change, volume_change, oi_change, oi_quantile
        )
        
        report = {
                'date': self.data.datetime.date(0).strftime('%Y-%m-%d'),
                'symbol_name': self.data._name or '未知商品',
                'symbol': self.params.symbol,
                'close_price': float(self.data.close[0]),
                'trend': current_trend,
                'trend_text': self.get_trend_text(current_trend),
                'trend_start_date': trend_info.get('trend_start_date', '未知'),
                'trend_start_price': float(trend_info.get('trend_start_price', 0)),
                'trend_duration': trend_info.get('trend_duration', 0),
                'rsi': round(float(self.rsi[0]), 2) if len(self.rsi) > 0 else 0,
                'atr': round(float(self.atr[0]), 3) if len(self.atr) > 0 else 0,
                'atr_percent': round((float(self.atr[0]) / float(self.data.close[0]) * 100), 2) if len(self.atr) > 0 and self.data.close[0] != 0 else 0,
                'force_index': round(current_force, 2),
                'adx': round(float(self.adx[0]), 2) if len(self.adx) > 0 else 0,
                
                # 新增持仓量相关字段
                'volume': float(self.volume[0]) if len(self.volume) > 0 else 0,
                'volume_change_pct': round(volume_change * 100, 2),
                'open_interest': current_oi,
                'oi_change_pct': round(oi_change * 100, 2),
                'oi_quantile': round(oi_quantile * 100, 2),
                'market_strength': market_strength_text,
                'market_strength_score': market_strength_score,
                'buy_signal': 0,
                'sell_signal': 0,
                'signal_strength': 0  # 信号强度 0-100
            }
    
        signal_strength = 0
        
        if current_trend == 1:  # 趋势向上
            if current_force < 0:
                report['force_status'] = "回调买入机会"
            elif current_force > 0:
                report['force_status'] = "强势上涨"
            else:
                report['force_status'] = "中性"
                
            conditions_met = 0            
            # 第一重：趋势确认（已满足）
            conditions_met += 1
            
            # 第二重：动量确认
            if self.adx[0] > 25:
                conditions_met += 1
                signal_strength += 30
            if current_force < 0:  # 力量指数为负表示回调，是买入机会
                conditions_met += 1
                signal_strength += 30
            
            # 第三重：时机选择
            if self.rsi[0] < 70:  # RSI不过热
                conditions_met += 1
                signal_strength += 20
            
            # 第四重：持仓量确认（新增）
            if market_strength_score > 0:  # 市场坚挺
                conditions_met += 1
                signal_strength += 30
                report['oi_signal'] = "持仓量支撑做多"
            elif market_strength_score < 0:
                report['oi_signal'] = "持仓量警示风险"
                signal_strength -= 20  # 持仓量信号负面，降低信号强度
            else:
                report['oi_signal'] = "持仓量中性"
            
            if conditions_met >= 3:  # 至少满足2个条件
                report['buy_signal'] = 1
                report['signal_strength'] = min(signal_strength + 20, 100)
                
        elif current_trend == -1:  # 趋势向下
            if current_force > 0:
                report['force_status'] = "反弹卖出机会"
            elif current_force < 0:
                report['force_status'] = "强势下跌"
            else:
                report['force_status'] = "中性"
                
            conditions_met = 0
            # 第一重：趋势确认（已满足）
            conditions_met += 1
            
            # 第二重：动量确认
            if self.adx[0] > 25:
                conditions_met += 1
                signal_strength += 30
            if current_force > 0:  # 力量指数为正表示反弹，是卖出机会
                conditions_met += 1
                signal_strength += 30
            
            # 第三重：时机选择
            if self.rsi[0] > 30:  # RSI不超卖
                conditions_met += 1
                signal_strength += 20
            
            # 第四重：持仓量确认（新增）
            if market_strength_score > 0:  # 市场坚挺（对空头是负面）
                report['oi_signal'] = "持仓量支撑坚挺，空头谨慎"
                signal_strength -= 20
            elif market_strength_score < 0:  # 市场疲软（对空头是正面）
                conditions_met += 1
                signal_strength += 30
                report['oi_signal'] = "持仓量支撑做空"
            else:
                report['oi_signal'] = "持仓量中性"
            
            if conditions_met >= 3:
                report['sell_signal'] = 1
                report['signal_strength'] = min(signal_strength + 20, 100)
        else:
            # 震荡趋势
            if current_force > 0:
                report['force_status'] = "短期强势"
            elif current_force < 0:
                report['force_status'] = "短期弱势"
            else:
                report['force_status'] = "中性"
        
        # 添加技术指标状态描述
        report['adx_strength'] = "强趋势" if report['adx'] > 25 else "弱趋势"
        
         # 持仓量状态描述
        if oi_quantile > 0.8:
            report['oi_status'] = "极端高位"
        elif oi_quantile > 0.7:
            report['oi_status'] = "高位"
        elif oi_quantile < 0.2:
            report['oi_status'] = "极端低位"
        elif oi_quantile < 0.3:
            report['oi_status'] = "低位"
        else:
            report['oi_status'] = "中位"
        
        return report
    
    def save_analysis_report(self, report):
        '''保存分析报告'''
        self.analysis_reports.append(report)
    
    def print_signal_report(self, report):
        '''打印信号报告'''
        print("\n" + "="*80)
        print(f"📊 三重过滤交易信号 - {report['date']}")
        print("="*80)
        print(f"商品: {report['symbol']} | 收盘价: {report['close_price']:.2f}")
        print(f"趋势: {report['trend_text']} | 开始日期: {report['trend_start_date']} | 开始价格: {report['trend_start_price']:.2f}")
        print("-"*80)
        print(f"技术指标:")
        print(f"  RSI: {report['rsi']:.1f}")
        print(f"  ATR: {report['atr']:.3f} ({report['atr_percent']:.2f}%)")
        print(f"  ADX: {report['adx']:.1f} ({report['adx_strength']})")
        print(f"  力量指数: {report['force_index']:.0f} ({report['force_status']})")
        print("-"*80)
        print(f"持仓量分析:")
        print(f"  成交量: {report['volume']:,.0f} ({report['volume_change_pct']:+.1f}%)")
        print(f"  持仓量: {report['open_interest']:,.0f} ({report['oi_change_pct']:+.1f}%)")
        print(f"  持仓分位数: {report['oi_quantile']:.1f}% ({report['oi_status']})")
        print(f"  市场强度: {report['market_strength']}")
        print(f"  持仓量信号: {report.get('oi_signal', '无')}")
        print("-"*80)
        
        if report['buy_signal'] == 1:
            print(f"🎯 买入信号 | 强度: {report['signal_strength']}%")
        elif report['sell_signal'] == 1:
            print(f"🎯 卖出信号 | 强度: {report['signal_strength']}%")
        else:
            print("⏸️  无交易信号")
        print("="*80)   
        
        
    def next(self):
        self.current_bar = len(self)  # 更新当前bar索引
                
        # # 打印状态检查
        # if self.current_bar % 50 == 0:
        #     self.log(f'🔍 状态检查: current_bar={self.current_bar}, entry_bar={self.entry_bar}, position={self.position.size if self.position else 0}, entry_price={self.entry_price}')
        
        # # 时间止损检查
        # if self.position and self.entry_bar > 0:
        #     hold_bars = self.current_bar - self.entry_bar
            
        #     if hold_bars == self.p.max_hold_days - 1:
        #         self.log(f'⚠️ 时间止损提醒: 已持仓{hold_bars}个bar，下一个bar将触发时间止损')
            
        #     if hold_bars >= self.p.max_hold_days:
        #         self.log(f'🕒 时间止损触发: 持仓{hold_bars}个bar')
        #         self.order = self.close()
        #         return
        
        if self.order:
            return
        
        report = self.tsts_analysis()
        self.save_analysis_report(report)
        
        # 开仓逻辑 - 只在没有持仓且没有挂单时开仓
        if not self.position and not self.order and self.entry_price == 0:
            if report['buy_signal'] == 1:
                self.order = self.buy(size=1)
                self.log(f'发出做多订单: 价格={self.data.close[0]:.2f}')
                
            elif report['sell_signal'] == 1:
                self.order = self.sell(size=1)
                self.log(f'发出做空订单: 价格={self.data.close[0]:.2f}')
        
        # # 移动止损检查 - 添加安全检查
        # if self.position and self.entry_price > 0:
        #     stop_triggered = self.calculate_trailing_stop()
        #     if stop_triggered:
        #         self.order = self.close()
        #         return
            
        # 原有的趋势反转平仓逻辑
        if self.position:
            if self.position.size > 0:  # 多头持仓
                force_exit = (self.force.lines.force[0] > 0 and 
                         self.force.lines.force[-1] > 0 and 
                         self.force.lines.force[-2] > 0 and
                         self.rsi[0] > 70)
                if force_exit:
                    self.order = self.close()
                    self.log('多头平仓: 力量指数反转')
                elif self.trend[0] != 1:
                    self.order = self.close()
                    self.log('多头平仓，周趋势反转')
                    
            elif self.position.size < 0:  # 空头持仓
                force_exit = (self.force.lines.force[0] < 0 and 
                         self.force.lines.force[-1] < 0 and 
                         self.force.lines.force[-2] < 0 and
                         self.rsi[0] < 30) 
                if force_exit:
                    self.order = self.close()
                    self.log('空头平仓: 力量指数反转')
                elif self.trend[0] != -1:
                    self.order = self.close()
                    self.log('空头平仓，周趋势反转')
        
    def stop(self):
        '''策略结束时保存最终报告'''
        if not self.analysis_reports:
            print("没有分析报告可保存")
            return
        
        if self.params.printlog is False:
            return
            
        # 获取最新报告
        latest = self.analysis_reports[-1]
        
        # 创建单行DataFrame并保存
        df = pd.DataFrame([latest])
        
        filename = f"triple_screen_latest_{self.data._name}_{self.data.datetime.date(0).strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        # 计算绩效指标
        initial_cash = self.broker.startingcash
        final_value = self.broker.getvalue()
        total_return_pct = (final_value - initial_cash) / initial_cash * 100
        
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0
        
        # 输出绩效报告
        print("\n" + "="*80)
        print("📈 策略绩效报告")
        print("="*80)
        print(f"初始资金: {initial_cash:,.2f}")
        print(f"最终资产: {final_value:,.2f}")
        print(f"总收益率: {total_return_pct:.2f}%")
        print(f"交易次数: {self.trade_count}")
        print(f"盈利次数: {self.win_count}")
        print(f"胜率: {win_rate:.2f}%")
        print(f"总盈亏: {self.total_return:,.2f}")
        print("="*80)
        
        # 保存交易记录
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            trades_filename = f"triple_screen_trades_{self.data._name}_{self.data.datetime.date(0).strftime('%Y%m%d')}.csv"
            trades_df.to_csv(trades_filename, index=False, encoding='utf-8-sig')
            print(f"交易记录已保存至: {trades_filename}")


    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            # 添加详细的状态日志
            self.log(f'🔍 订单完成检查: size={order.executed.size}, position={self.position.size if self.position else None}')
            
            # 判断订单类型 - 基于订单执行前的持仓状态
            if order.isbuy():
                # 买入订单：可能是开多仓或平空仓
                if hasattr(self, 'position_direction') and self.position_direction == '空头':
                    order_type = "买入平空仓"
                    action_desc = "平仓"
                else:
                    order_type = "买入开多仓"
                    action_desc = "开仓"
            elif order.issell():
                # 卖出订单：可能是开空仓或平多仓
                if hasattr(self, 'position_direction') and self.position_direction == '多头':
                    order_type = "卖出平多仓"
                    action_desc = "平仓"
                else:
                    order_type = "卖出开空仓"
                    action_desc = "开仓"
            else:
                order_type = "未知订单"
                action_desc = "未知"
            
            # 关键修复：只在开仓时设置entry_price
            if abs(order.executed.size) > 0:
                # 检查是否是开仓订单 - 使用更严格的判断条件
                is_opening = (action_desc == "开仓" and 
                            self.entry_price == 0)  # 只有entry_price为0时才认为是开仓
                
                if is_opening:
                    self.entry_bar = len(self)
                    self.entry_price = order.executed.price
                    self.entry_date = self.data.datetime.date(0)
                    
                    if order_type == "买入开多仓":
                        self.position_direction = '多头'
                        self.log(f'✅ 多头开仓完成: 价格={order.executed.price:.2f}, entry_bar={self.entry_bar}, entry_price={self.entry_price:.2f}')
                    elif order_type == "卖出开空仓":
                        self.position_direction = '空头' 
                        self.log(f'✅ 空头开仓完成: 价格={order.executed.price:.2f}, entry_bar={self.entry_bar}, entry_price={self.entry_price:.2f}')
                    
                    self.reset_stop_variables()
                    self.position_opened = True
                else:
                    self.log(f'⚠️ 跳过开仓设置: position_direction={getattr(self, "position_direction", None)}, entry_price={self.entry_price}')
            
            # 记录订单详情 - 使用清晰的订单类型描述
            cost_sign = "" if order.executed.value >= 0 else "-"
            self.log(f'📋 {order_type}完成: 价格={order.executed.price:.2f}, 成本={cost_sign}{abs(order.executed.value):.2f}, 手续费={order.executed.comm:.2f}')
                    
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            status_name = order.getstatusname()
            if order.status == order.Canceled:
                self.log(f'❌ 订单取消: {status_name}')
            elif order.status == order.Margin:
                self.log(f'💰 保证金不足: {status_name}')
            elif order.status == order.Rejected:
                self.log(f'🚫 订单拒绝: {status_name}')
        
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            # 直接使用Backtrader系统计算的准确数据
            self.log(f'🔍 交易结算详情:')
            self.log(f'  入场价: {self.entry_price:.2f}')
            self.log(f'  持仓方向: {self.position_direction}')
            self.log(f'  开仓日期: {trade.dtopen}')
            self.log(f'  平仓日期: {trade.dtclose}')
            self.log(f'  持仓周期: {trade.barlen}个bar')
            
            # 使用系统计算的准确盈亏数据
            system_pnl = trade.pnl
            system_commission = trade.commission
            system_net_pnl = trade.pnlcomm
            
            # 计算收益率（基于入场价和系统盈亏）
            if self.entry_price != 0:
                # 收益率 = 净利润 / (入场价 × 持仓数量)
                # 假设固定1手，使用系统盈亏反推有效数量
                effective_quantity = abs(system_pnl / (self.entry_price * 0.01)) if system_pnl != 0 else 1
                profit_pct = (system_net_pnl / (self.entry_price * effective_quantity)) * 100
            else:
                profit_pct = 0
            
            self.log(f'  系统毛利润: {system_pnl:.2f}')
            self.log(f'  系统手续费: {system_commission:.2f}')
            self.log(f'  系统净利润: {system_net_pnl:.2f}')
            self.log(f'  收益率: {profit_pct:.2f}%')
            
            # 更新统计 - 使用系统数据
            self.trade_count += 1
            if system_pnl > 0:
                self.win_count += 1
            self.total_return += system_pnl
            
            # 记录交易
            try:
                trade_record = {
                    'date': self.data.datetime.date(0).strftime('%Y-%m-%d'),
                    'direction': self.position_direction or '未知',
                    'entry_price': round(self.entry_price, 2),
                    'exit_price': round(self.entry_price + (system_pnl if self.position_direction == '多头' else -system_pnl), 2),
                    'pnl': round(system_pnl, 2),
                    'pnl_percent': round(profit_pct, 2),
                    'commission': round(system_commission, 2),
                    'net_pnl': round(system_net_pnl, 2),
                    'entry_date': self.entry_date.strftime('%Y-%m-%d') if self.entry_date else '未知',
                    'hold_bars': trade.barlen,
                    'open_date': trade.dtopen.strftime('%Y-%m-%d') if hasattr(trade.dtopen, 'strftime') else str(trade.dtopen),
                    'close_date': trade.dtclose.strftime('%Y-%m-%d') if hasattr(trade.dtclose, 'strftime') else str(trade.dtclose)
                }
                self.trades.append(trade_record)
                
                self.log(f'📊 平仓: 毛利润={system_pnl:.2f}, 净利润={system_net_pnl:.2f}, 收益率={profit_pct:.2f}%')
                
            except Exception as e:
                self.log(f'❌ 记录交易时出错: {e}')
            
            # 重置所有状态
            self.entry_price = 0
            self.entry_date = None
            self.position_direction = None
            self.trailing_stop = 0
            self.peak_price = 0
            self.entry_bar = 0
            self.position_opened = False
            self.pending_close = False
            self.log(f'🔄 状态已重置: entry_price={self.entry_price}, direction={self.position_direction}')