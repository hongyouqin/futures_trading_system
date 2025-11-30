import backtrader as bt
import akshare as ak
import numpy as np
from custom_indicators.mac_indicator import MovingAverageCrossOver
from custom_indicators.force_indicator import ForceIndex
from custom_indicators.dynamic_value_channel import DynamicValueChannel

import pandas as pd
import warnings
warnings.filterwarnings('ignore')

'''
    日内三重过滤系统交易信号生成器
    基于亚历山大·埃尔德的三重滤网交易系统原理
    第一重：1小时数据判断趋势方向
    第二重：15分钟数据寻找交易机会  
    第三重：RSI离场时机
'''

class DayTradingSignalGenerator(bt.Strategy):
    params = (
        ('fi_period', 2),           # ForceIndex计算周期
        ('atr_period', 14),         # ATR计算周期
        ('rsi_period', 14),         # RSI计算周期
        ('short_ma_period', 8),   # 短期均线周期
        ('long_ma_period', 21),    # 长期均线周期
        ('risk_per_trade', 0.02),   # 每笔交易风险比例
        ('trail_percent', 0.1),     # 移动止损百分比
        ('debug', True),            # 调试模式
        ('generate_signals_only', False),  # 仅生成信号，不执行交易
        ('rsi_exit_threshold', 70), # RSI离场阈值
        ('oi_lookback', 150*5),         # 持仓量分位数计算周期（5年）
        ('oi_threshold', 0.7),        # 持仓量高位阈值
        ('channel_coeff', 0.152579),
        ('channel_window', 60),
    )
    
    def __init__(self):
        # 第一重滤网：1小时数据判断趋势方向
        self.trend_indicator = MovingAverageCrossOver(self.data1)
        
        # 第二重滤网：15分钟数据寻找交易机会
        self.force_index = ForceIndex(self.data, period=self.params.fi_period)
        self.ema_fast = bt.indicators.EMA(self.data, period=self.params.short_ma_period)
        self.ema_slow = bt.indicators.EMA(self.data, period=self.params.long_ma_period)
        
        # 第三重滤网：RSI用于离场时机
        self.rsi = bt.indicators.RSI(self.data, period=self.params.rsi_period)
        
        # 波动性指标
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        
        # 动态价值通道指标 - 这会自动显示在主图上
        self.value_channel = DynamicValueChannel(
            self.data,
            slow_period=self.p.long_ma_period,
            channel_window=self.p.channel_window,
            initial_coeff=self.p.channel_coeff
        )
        
        # 持仓量分析指标
        self.volume = self.data.volume
        self.open_interest = self.data.openinterest
        # 持仓量历史数据存储
        self.oi_history = []
        self.volume_history = []
        
        # 信号状态跟踪
        self.signal = None
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.entry_time = None
        
        # 绩效跟踪
        self.trades = []
        self.signals_log = []
        self.recent_signals = []  # 存储最近信号

    def log(self, txt, dt=None):
        '''日志函数'''
        if self.params.debug:
            dt = dt or self.datas[0].datetime.datetime(0)
            print(f'{dt.isoformat()} {txt}')

    def notify_order(self, order):
        '''订单状态通知'''
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'多头入场: 价格={order.executed.price:.2f}, 成本={order.executed.value:.2f}, 佣金={order.executed.comm:.2f}')
            elif order.issell():
                self.log(f'空头入场: 价格={order.executed.price:.2f}, 成本={order.executed.value:.2f}, 佣金={order.executed.comm:.2f}')
                
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/被拒绝')

    def notify_trade(self, trade):
        '''交易结果通知'''
        if trade.isclosed:
            self.log(f'交易平仓, 毛利润={trade.pnl:.2f}, 净利润={trade.pnlcomm:.2f}')
            self.trades.append({
                'entry': trade.price,
                'exit': trade.price + trade.pnl,
                'pnl': trade.pnlcomm,
                'date': self.datas[0].datetime.datetime(0)
            })

    def calculate_position_size(self, price, stop_loss):
        '''基于风险的仓位计算'''
        risk_amount = self.broker.getvalue() * self.params.risk_per_trade
        price_risk = abs(price - stop_loss)
        
        if price_risk > 0:
            size = risk_amount / price_risk
            return int(size)
        return 0
    
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

    def calculate_oi_quantile(self, current_oi, lookback_period=150):
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

    def generate_signal(self):
        
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
        
        # 更新价值通道
        current_up_channel = self.value_channel.lines.up_channel[0]
        current_down_channel = self.value_channel.lines.down_channel[0]
        
        '''生成交易信号'''
        current_price = self.data.close[0]
        current_time = self.datas[0].datetime.datetime(0)
        
        # 第一重滤网：趋势判断
        trend_direction = self.trend_indicator[0]
        
        # 第二重滤网：动量确认
        force_value = self.force_index[0]
        
        # 第三重滤网：入场时机
        ema_fast = self.ema_fast[0]
        ema_slow = self.ema_slow[0]
        rsi_value = self.rsi[0]
        
        price_above_fast = current_price > ema_fast
        price_above_slow = current_price > ema_slow
        price_below_fast = current_price < ema_fast
        price_below_slow = current_price < ema_slow
        
        
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
        
        
        signal_info = {
            'timestamp': current_time,
            'trend': trend_direction,
            'force_index': force_value,
            'price': current_price,
            'ema_fast': ema_fast,
            'ema_slow': ema_slow,
            'rsi': rsi_value,
            'atr': round(self.atr[0], 2),
            'signal': 0,
            'signal_type': 'HOLD',
            'market_strength': market_strength_text,
            'market_strength_score': market_strength_score,
            'value_up_channel' : round(current_up_channel, 2),
            'value_down_channel' : round(current_down_channel, 2),
        }
                
        # 多头信号逻辑
        if trend_direction == 1:  # 上升趋势
            if force_value < 0 and rsi_value < 65:   # 动量确认
                if price_above_fast and price_above_slow:  # 价格在双EMA之上
                    signal_info['signal'] = 1
                    signal_info['signal_type'] = 'LONG'
                    self.log('*** 生成多头信号 ***')
        
        # 空头信号逻辑  
        elif trend_direction == -1:  # 下降趋势
            if force_value > 0 and rsi_value > 40:      # 动量确认
                if price_below_fast and price_below_slow:  # 价格在双EMA之下
                    signal_info['signal'] = -1
                    signal_info['signal_type'] = 'SHORT'
                    self.log('*** 生成空头信号 ***')
        
        # 存储最近信号（仅存储有意义的信号）
        if signal_info['signal'] != 0:
            self.recent_signals.append(signal_info)
            # 只保留最近10个信号
            if len(self.recent_signals) > 10:
                self.recent_signals.pop(0)
        
        self.signals_log.append(signal_info)
        return signal_info

    def should_exit_position(self):
        '''判断是否应该离场'''
        if not self.position:
            return False
            
        # current_price = self.data.close[0]
        rsi_value = self.rsi[0]
        # current_time = self.datas[0].datetime.datetime(0)
        
        # 持仓时间检查（避免过夜持仓）
        # if self.entry_time and (current_time - self.entry_time).total_seconds() > 3600 * 4:  # 4小时强制平仓
        #     self.log('达到最大持仓时间，强制平仓')
        #     return True
        
        # 基于RSI的离场逻辑
        if self.position.size > 0:  # 多头持仓
            if rsi_value > self.params.rsi_exit_threshold:  # RSI超买离场
                self.log(f'多头RSI超买离场: RSI={rsi_value:.2f}')
                return True
                
        elif self.position.size < 0:  # 空头持仓
            if rsi_value < (100 - self.params.rsi_exit_threshold):  # RSI超卖离场
                self.log(f'空头RSI超卖离场: RSI={rsi_value:.2f}')
                return True
        
        return False

    def execute_entry(self, signal_info):
        '''执行入场'''
        if self.params.generate_signals_only:
            self.log(f'信号模式: 检测到{signal_info["signal_type"]}信号，价格={signal_info["price"]:.2f}')
            return
            
        price = signal_info['price']
        
        if signal_info['signal'] == 1:  # 多头入场
            stop_loss = price - 2 * self.atr[0]  # 基于ATR的止损
            size = self.calculate_position_size(price, stop_loss)
            
            if size > 0:
                self.buy(size=3)
                self.stop_loss = stop_loss
                self.entry_price = price
                self.entry_time = self.datas[0].datetime.datetime(0)
                self.log(f'执行多头入场: 价格={price:.2f}, 仓位={size}, 止损={stop_loss:.2f}')
        
        elif signal_info['signal'] == -1:  # 空头入场
            stop_loss = price + 2 * self.atr[0]  # 基于ATR的止损
            size = self.calculate_position_size(price, stop_loss)
            
            if size > 0:
                self.sell(size=3)
                self.stop_loss = stop_loss
                self.entry_price = price
                self.entry_time = self.datas[0].datetime.datetime(0)
                self.log(f'执行空头入场: 价格={price:.2f}, 仓位={size}, 止损={stop_loss:.2f}')

    def manage_position(self):
        '''持仓管理'''
        if not self.position:
            return
            
        # current_price = self.data.close[0]
        
        # 检查RSI离场条件
        if self.should_exit_position():
            self.close()
            return
            
        # # 移动止损逻辑
        # if self.position.size > 0:  # 多头持仓
        #     new_stop = current_price * (1 - self.params.trail_percent/100)
        #     self.stop_loss = max(self.stop_loss, new_stop)
            
        #     if current_price <= self.stop_loss:
        #         self.close()
        #         self.log(f'多头止损: 价格={current_price:.2f}, 止损={self.stop_loss:.2f}')
                
        # elif self.position.size < 0:  # 空头持仓
        #     new_stop = current_price * (1 + self.params.trail_percent/100)
        #     self.stop_loss = min(self.stop_loss, new_stop)
            
        #     if current_price >= self.stop_loss:
        #         self.close()
        #         self.log(f'空头止损: 价格={current_price:.2f}, 止损={self.stop_loss:.2f}')

    def next(self):
        '''主逻辑循环'''
        # 如果有持仓，先执行持仓管理
        if self.position:
            self.manage_position()
        
        # 生成交易信号
        signal_info = self.generate_signal()
        
        # 执行入场（如果没有持仓）
        if not self.position and signal_info['signal'] != 0:
            self.execute_entry(signal_info)

    def stop(self):
        '''策略结束'''
        self.log('策略运行结束')
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t['pnl'] > 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # 计算盈亏比
        total_profit = 0
        total_loss = 0
        profit_trades = []
        loss_trades = []
        
        for trade in self.trades:
            if trade['pnl'] > 0:
                total_profit += trade['pnl']
                profit_trades.append(trade['pnl'])
            else:
                total_loss += abs(trade['pnl'])
                loss_trades.append(trade['pnl'])
        
        # 计算平均盈利和平均亏损
        avg_profit = total_profit / len(profit_trades) if profit_trades else 0
        avg_loss = total_loss / len(loss_trades) if loss_trades else 0
        
        # 计算盈亏比
        if avg_loss > 0:
            profit_loss_ratio = avg_profit / avg_loss
        else:
            profit_loss_ratio = float('inf') if avg_profit > 0 else 0
        
        # 计算总盈亏比（总盈利/总亏损）
        if total_loss > 0:
            total_profit_loss_ratio = total_profit / total_loss
        else:
            total_profit_loss_ratio = float('inf') if total_profit > 0 else 0
        
        self.log(f'总交易次数: {total_trades}')
        self.log(f'胜率: {win_rate:.2%}')
        self.log(f'盈利交易: {len(profit_trades)} 次')
        self.log(f'亏损交易: {len(loss_trades)} 次')
        self.log(f'总盈利: {total_profit:.2f}')
        self.log(f'总亏损: {total_loss:.2f}')
        self.log(f'平均盈利: {avg_profit:.2f}')
        self.log(f'平均亏损: {avg_loss:.2f}')
        self.log(f'盈亏比 (平均): {profit_loss_ratio:.2f}')
        self.log(f'盈亏比 (总): {total_profit_loss_ratio:.2f}')
        self.log(f'净利润: {total_profit - total_loss:.2f}')
        
        # 输出信号统计
        total_signals = len([s for s in self.signals_log if s['signal'] != 0])
        long_signals = len([s for s in self.signals_log if s['signal'] == 1])
        short_signals = len([s for s in self.signals_log if s['signal'] == -1])
        
        self.log(f'总信号数: {total_signals} (多头: {long_signals}, 空头: {short_signals})')
        
        # 输出最近信号
        self.log('最近交易信号:')
        for signal in self.recent_signals[-5:]:  # 显示最近5个信号
            self.log(f"  时间: {signal['timestamp']}, 类型: {signal['signal_type']}, "
                    f"价格: {signal['price']:.2f}, RSI: {signal['rsi']:.2f}")

    def stop2(self):
        '''策略结束'''
        self.log('策略运行结束')
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t['pnl'] > 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        self.log(f'总交易次数: {total_trades}')
        self.log(f'胜率: {win_rate:.2%}')
        
        # 输出信号统计
        total_signals = len([s for s in self.signals_log if s['signal'] != 0])
        long_signals = len([s for s in self.signals_log if s['signal'] == 1])
        short_signals = len([s for s in self.signals_log if s['signal'] == -1])
        
        self.log(f'总信号数: {total_signals} (多头: {long_signals}, 空头: {short_signals})')
        
        # 输出最近信号
        self.log('最近交易信号:')
        for signal in self.recent_signals[-5:]:  # 显示最近5个信号
            self.log(f"  时间: {signal['timestamp']}, 类型: {signal['signal_type']}, "
                    f"价格: {signal['price']:.2f}, RSI: {signal['rsi']:.2f}")

    def get_recent_signals(self, count=5):
        '''获取最近交易信号'''
        return self.recent_signals[-count:] if self.recent_signals else []


class FuturesDataFeed(bt.feeds.PandasData):
    """适配期货数据的Backtrader数据源"""
    params = (
        ('datetime', 'datetime'),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', 'hold'),
    )


def run_strategy_with_signals(symbol='SA0', initial_cash=100000.0, generate_signals_only=True, debug_mode = False):
    """
    运行策略并返回交易信号
    
    Parameters:
    -----------
    symbol : str
        交易品种代码
    initial_cash : float
        初始资金
    generate_signals_only : bool
        是否仅生成信号而不执行交易
    
    Returns:
    --------
    dict : 包含策略结果和交易信号的信息
    """
    try:
        # 这里使用您提供的数据获取代码
        df_15min = ak.futures_zh_minute_sina(symbol=symbol, period=15)
        df_1hour = ak.futures_zh_minute_sina(symbol=symbol, period=60)
        
        # 数据预处理
        df_15min['datetime'] = pd.to_datetime(df_15min['datetime'])
        df_15min = df_15min.sort_values('datetime')
        
        df_1hour['datetime'] = pd.to_datetime(df_1hour['datetime'])
        df_1hour = df_1hour.sort_values('datetime')
        
        print(f"30分钟数据: {df_15min.tail()}")
        print(f"1小时数据: {df_1hour.tail()}")        
        
        # 创建数据源
        data_15min = FuturesDataFeed(dataname=df_15min)
        data_1hour = FuturesDataFeed(dataname=df_1hour)
        
        # print(df_15min)
        # 创建回测引擎
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.0005)
        
        # 添加数据
        cerebro.adddata(data_15min)  # 主数据（15分钟）
        cerebro.adddata(data_1hour)  # 趋势数据（1小时）
         
        # 添加策略
        cerebro.addstrategy(DayTradingSignalGenerator, 
                          generate_signals_only=generate_signals_only,
                          debug=debug_mode)
        
        # 运行策略
        print(f'初始资金: {cerebro.broker.getvalue():.2f}')
        strategies = cerebro.run()
        print(f'最终资金: {cerebro.broker.getvalue():.2f}')
        
        # 获取策略实例和信号
        strategy_instance = strategies[0]
        recent_signals = strategy_instance.get_recent_signals(5)
        
        result = {
            'initial_cash': initial_cash,
            'final_cash': cerebro.broker.getvalue(),
            'total_trades': len(strategy_instance.trades),
            'recent_signals': recent_signals,
            'all_signals': strategy_instance.signals_log[-20:],  # 最近20个信号
            'performance': {
                'win_rate': len([t for t in strategy_instance.trades if t['pnl'] > 0]) / len(strategy_instance.trades) if strategy_instance.trades else 0,
                'total_signals': len([s for s in strategy_instance.signals_log if s['signal'] != 0])
            }
        }
        
        return result
        
    except Exception as e:
        print(f"策略运行错误: {e}")
        return None


def print_signals_summary(result):
    """打印信号摘要"""
    if not result or not result['recent_signals']:
        print("没有生成交易信号")
        return
    
    print("\n" + "="*50)
    print("最近交易信号摘要")
    print("="*50)
    
    for i, signal in enumerate(result['recent_signals']):
        print(f"{i+1}. 时间: {signal['timestamp']}")
        print(f"   信号: {signal['signal_type']}")
        print(f"   价格: {signal['price']:.2f}")
        print(f"   RSI: {signal['rsi']:.2f}")
        print(f"   趋势: {'上涨' if signal['trend'] == 1 else '下跌' if signal['trend'] == -1 else '震荡'}")
        print(f"   力度指数: {signal['force_index']:.2f}")
        print(f"   市場强度: {signal['market_strength']}")
        print(f"   市場分数: {signal['market_strength_score']}")
        print(f"   价值上通道: {signal['value_up_channel']}")
        print(f"   价值下通道: {signal['value_down_channel']}")
        
        print("-" * 30)


